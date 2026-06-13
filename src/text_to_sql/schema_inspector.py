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

from dataclasses import dataclass
from typing import List

from llm_router_ledger import (
    load_config,
    send_message,
    UsageTracker,
)

from text_to_sql.app_logger import get_logger
from text_to_sql.prompts.prompts import get_prompt


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


def _tier2_llm_scan(
    ddl: str,
    tracker: UsageTracker | None = None,
) -> List[Finding]:
    """
    Helper function used to run Tier 2 LLM
    inspection on the DDL. Only called when
    Tier 1 finds nothing.

    Uses the schema_inspector role endpoint
    from llm_endpoints.yaml. When tracker is
    provided, paired llm_request / llm_response
    events are appended to its JSONL log.
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

        content, _, _ = send_message(
            endpoint_name=ep.name,
            system=get_prompt("schema_inspector"),
            user=ddl,
            config=config,
            tracker=tracker,
            purpose="schema_inspector",
            metadata={"question": "schema_ddl_inspection"},
            temperature=0.0,
            max_tokens=500,
            user_id=os.environ.get("OPENROUTER_RUN_TAG") or None,
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
    tracker: UsageTracker | None = None,
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
        tracker: Optional UsageTracker; when
            provided the Tier 2 LLM call is
            logged as paired llm_request /
            llm_response events.

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
    findings = _tier2_llm_scan(ddl=ddl, tracker=tracker)
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
