"""
Schema Inspector: two-tier DDL inspection for
adversarial schema modifications.

Tier 1 (regex): fast, deterministic scan for SQL
fragments, suspicious column names, and injection
patterns in column definitions and DEFAULT values.

Tier 2 (LLM): only invoked when Tier 1 finds
nothing. Sends DDL to a language model to detect
subtle adversarial elements (e.g. natural-language
instructions embedded in DEFAULT values).

Usage:
    from text_to_sql.schema_inspector import (
        inspect_schema,
    )

    findings = inspect_schema(ddl="CREATE TABLE ...")
"""

import json
import os
import re
import time

from dataclasses import dataclass
from typing import List

from text_to_sql.app_logger import get_logger
from text_to_sql.llm_config import (
    get_client,
    get_model_name,
    load_config,
)
from text_to_sql.prompts.prompts import get_prompt
from text_to_sql.usage_tracker import log_llm_response


logger = get_logger(__name__)


@dataclass
class Finding:
    """
    A single suspicious element found during
    schema inspection.
    """

    table: str
    column: str
    reason: str
    tier: int
    snippet: str = ""


# ------------------------------------------------
# Tier 1: regex patterns
# ------------------------------------------------

_SQL_KEYWORDS = re.compile(
    r"\b(SELECT|INSERT|UPDATE|DELETE|DROP|UNION"
    r"|EXEC|EXECUTE|TRUNCATE|ALTER)\b",
    re.IGNORECASE,
)

_SQL_COMMENT = re.compile(r"--")

_SQL_SEMICOLON = re.compile(r";")

_SUSPICIOUS_NAMES = re.compile(
    r"\b(malicious|inject|payload|exploit"
    r"|sensitive_data|ssn|hack)\b",
    re.IGNORECASE,
)

_INSTRUCTION_PATTERNS = re.compile(
    r"\b(always\s+join|also\s+select"
    r"|ignore\s+access|ignore\s+security"
    r"|override|bypass)\b",
    re.IGNORECASE,
)

# Match column definitions inside CREATE TABLE.
# Group 1: column name (possibly double-quoted).
# Group 2: rest of the definition up to comma,
#   closing paren, or next column.
_COLUMN_DEF = re.compile(
    r"^\s+"
    r"(\"[^\"]+\"|[a-zA-Z_]\w*)"
    r"\s+"
    r"((?:VARCHAR|TEXT|INT|INTEGER|DECIMAL|NUMERIC"
    r"|BOOLEAN|TIMESTAMP|DATE|FLOAT|DOUBLE"
    r"|BIGINT|SMALLINT|REAL|JSONB|JSON|CHAR"
    r"|UUID|SERIAL|BYTEA)"
    r"(?:\([^)]*\))?"
    r"[^,)]*)",
    re.IGNORECASE | re.MULTILINE,
)


def _parse_llm_response(
    content: str,
) -> List[Finding]:
    """
    Helper function used to parse the LLM
    response into Finding objects. Expects JSON
    array of {table, column, reason} objects.
    """
    content = content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```\w*\n?", "", content)
        content = re.sub(r"\n?```$", "", content)
        content = content.strip()

    try:
        items = json.loads(content)
    except json.JSONDecodeError:
        if "no suspicious" in content.lower():
            return []
        if "clean" in content.lower():
            return []
        logger.warning(
            "Tier 2 response not JSON: %s",
            content[:200],
        )
        return []

    if not isinstance(items, list):
        items = [items]

    findings: List[Finding] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        findings.append(Finding(
            table=item.get("table", "unknown"),
            column=item.get("column", "unknown"),
            reason=item.get("reason", "LLM flag"),
            tier=2,
            snippet=item.get("snippet", ""),
        ))
    return findings


def _scan_column(
    table: str,
    col_name: str,
    col_def: str,
) -> List[Finding]:
    """
    Helper function used to scan a single column
    definition for suspicious patterns.
    """
    findings: List[Finding] = []

    if _SQL_KEYWORDS.search(col_name):
        findings.append(Finding(
            table=table,
            column=col_name,
            reason="SQL keyword in column name",
            tier=1,
            snippet=col_name,
        ))

    if _SQL_COMMENT.search(col_name):
        findings.append(Finding(
            table=table,
            column=col_name,
            reason="SQL comment marker in column name",
            tier=1,
            snippet=col_name,
        ))

    if _SUSPICIOUS_NAMES.search(col_name):
        findings.append(Finding(
            table=table,
            column=col_name,
            reason="Suspicious column name",
            tier=1,
            snippet=col_name,
        ))

    # Scan DEFAULT value for SQL/instructions
    default_match = re.search(r"DEFAULT\s+'([^']*)'", col_def, re.IGNORECASE)
    if default_match:
        default_val = default_match.group(1)
        if _SQL_KEYWORDS.search(default_val):
            findings.append(Finding(
                table=table,
                column=col_name,
                reason="SQL keyword in DEFAULT value",
                tier=1,
                snippet=default_val,
            ))
        if _SQL_COMMENT.search(default_val):
            findings.append(Finding(
                table=table,
                column=col_name,
                reason="SQL comment marker in DEFAULT",
                tier=1,
                snippet=default_val,
            ))
        if _SQL_SEMICOLON.search(default_val):
            findings.append(Finding(
                table=table,
                column=col_name,
                reason="Semicolon in DEFAULT value",
                tier=1,
                snippet=default_val,
            ))
        if _INSTRUCTION_PATTERNS.search(default_val):
            findings.append(Finding(
                table=table,
                column=col_name,
                reason="Instruction pattern in DEFAULT",
                tier=1,
                snippet=default_val,
            ))

    if _INSTRUCTION_PATTERNS.search(col_name):
        findings.append(Finding(
            table=table,
            column=col_name,
            reason="Instruction pattern in column name",
            tier=1,
            snippet=col_name,
        ))

    return findings


def _tier1_scan(ddl: str) -> List[Finding]:
    """
    Helper function used to run Tier 1 regex
    inspection across all CREATE TABLE blocks.
    """
    findings: List[Finding] = []
    block_pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(\w+)\s*\((.*?)\);",
        re.DOTALL | re.IGNORECASE,
    )
    for block in block_pattern.finditer(ddl):
        table = block.group(1).lower()
        body = block.group(2)
        for col in _COLUMN_DEF.finditer(body):
            col_name = col.group(1)
            col_def = col.group(2)
            findings.extend(_scan_column(
                table=table,
                col_name=col_name,
                col_def=col_def,
            ))
    return findings


def _tier2_llm_scan(ddl: str) -> List[Finding]:
    """
    Helper function used to run Tier 2 LLM
    inspection on the DDL. Only called when
    Tier 1 finds nothing.

    Uses the schema_inspector role endpoint
    from llm_endpoints.yaml.
    """
    try:
        config = load_config()
        eps = config.get_role_endpoints(
            project="default",
            role="schema_inspector",
        )
        if not eps:
            logger.warning(
                "No schema_inspector endpoint configured, skipping Tier 2")
            return []
        ep = eps[0]
        logger.info(
            "Tier 2: %s via %s", ep.model, ep.provider)

        client = get_client(
            endpoint_name=ep.name,
            config=config,
        )
        model = get_model_name(
            endpoint_name=ep.name,
            config=config,
        )
        prompt = get_prompt("schema_inspector")
        create_kwargs: dict = {
            "model": model,
            "messages": [
                {
                    "role": "system",
                    "content": prompt,
                },
                {
                    "role": "user",
                    "content": ddl,
                },
            ],
            "temperature": 0.0,
            "max_tokens": 500,
        }
        run_tag = os.environ.get("OPENROUTER_RUN_TAG", "")
        if run_tag:
            create_kwargs["user"] = run_tag
        response = client.chat.completions.create(**create_kwargs)

        u = response.usage
        gen_id = getattr(response, "id", "")
        content = response.choices[0].message.content or ""

        if u:
            log_llm_response(
                request_id=f"si-{int(time.time())}",
                model=model,
                question="schema_ddl_inspection",
                usage={
                    "prompt_tokens": u.prompt_tokens,
                    "completion_tokens": u.completion_tokens,
                },
                generated_sql=content,
                purpose="schema_inspector",
                generation_id=gen_id,
            )
        return _parse_llm_response(content=content)

    except Exception as e:
        logger.error(
            "Schema inspection Tier 2 failed: %s",
            e,
        )
        return []


def inspect_schema(
    ddl: str,
    skip_tier2: bool = False,
) -> List[Finding]:
    """
    Run two-tier schema inspection on DDL.

    Tier 1 (regex) runs first. If it finds
    suspicious elements, returns immediately.
    Tier 2 (LLM) runs only when Tier 1 finds
    nothing, unless skip_tier2 is True.

    Args:
        ddl: Schema DDL string (CREATE TABLE
            blocks)
        skip_tier2: Skip LLM inspection

    Returns:
        List of Finding objects
    """
    logger.info("Schema inspection: Tier 1 (regex)")
    findings = _tier1_scan(ddl=ddl)
    if findings:
        logger.info(
            "Schema inspection: Tier 1 found "
            "%d suspicious element(s)",
            len(findings),
        )
        return findings

    logger.info("Schema inspection: Tier 1 clean")

    if skip_tier2:
        logger.info("Schema inspection: Tier 2 skipped")
        return []

    logger.info("Schema inspection: Tier 2 (LLM)")
    findings = _tier2_llm_scan(ddl=ddl)
    if findings:
        logger.info(
            "Schema inspection: Tier 2 found "
            "%d suspicious element(s)",
            len(findings),
        )
    else:
        logger.info(
            "Schema inspection: Tier 2 clean"
        )
    return findings
