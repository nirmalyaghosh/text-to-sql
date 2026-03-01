"""
Demo: End-to-end validation of schema pruning.

Usage:
    python demos/05_schema_pruning_e2e_validation.py
    python demos/05_schema_pruning_e2e_validation.py --verbose
    python demos/05_schema_pruning_e2e_validation.py --query GQ-002

Compares full-schema vs pruned-schema SQL generation pipelines:
for each golden query, generates SQL using the LLM with both
the full schema and the pruned schema, executes both against the
database, and compares execution outcomes.

Note: this validates that pruning does not degrade SQL generation
relative to the full-schema baseline. It does not validate
correctness against ground-truth query results.

Requires: OPENAI_API_KEY and DATABASE_URL in .env
"""

import argparse
import json
import logging
import os
import random
import re
import statistics
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import (
    Dict,
    List,
    Tuple,
)

from dotenv import load_dotenv
from openai import OpenAI

from text_to_sql.app_logger import get_logger, setup_logging
from text_to_sql.db import execute_query, get_schema_ddl
from text_to_sql.prompts.prompts import get_prompt
from text_to_sql.schema_pruner import SchemaPruner
from text_to_sql.usage_tracker import (
    generate_run_id,
    log_llm_request,
    log_llm_response,
)


load_dotenv()

logger = get_logger(__name__)

EVALS_DIR = Path(__file__).parent.parent / "evals"
LOGS_DIR = Path(__file__).parent.parent / "logs"
SCHEMA_DIR = Path(__file__).parent.parent / "schema"

SYSTEM_PROMPT = get_prompt("naive")


def load_golden_queries() -> List[Dict]:
    """
    Load golden queries from evals directory.
    """
    path = EVALS_DIR / "golden_queries.json"
    return json.loads(path.read_text(encoding="utf-8"))


def load_schema_ddl() -> str:
    """
    Load full schema DDL from schema directory.
    """
    path = SCHEMA_DIR / "schema_setup.sql"
    return path.read_text(encoding="utf-8")


def generate_sql(
    question: str,
    schema: str,
    client: OpenAI,
    model: str,
) -> Tuple[str, Dict]:
    """
    Helper function used to generate SQL from a question
    and schema context.

    Mirrors the naive pipeline but accepts a custom schema,
    allowing comparison between full and pruned schemas.

    Returns (sql, usage) where usage has prompt_tokens,
    completion_tokens, total_tokens.
    """
    user_content = f"Schema:\n{schema}\n\nQuestion: {question}"

    request_id = log_llm_request(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_content,
        question=question,
    )

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )
    sql = response.choices[0].message.content.strip()

    usage = (
        response.usage.model_dump() if response.usage else {}
    )

    log_llm_response(
        request_id=request_id,
        model=model,
        question=question,
        usage=usage,
        generated_sql=sql,
    )

    # Clean markdown fencing if the LLM wraps it
    if sql.startswith("```"):
        sql = "\n".join(sql.split("\n")[1:-1])

    return sql, usage


def execute_sql_safe(sql: str) -> Dict:
    """
    Helper function used to execute SQL and return result
    or error.

    Returns dict with 'success', 'rows', 'row_count', 'error'.
    """
    try:
        rows = execute_query(sql)
        return {
            "success": True,
            "rows": rows,
            "row_count": len(rows),
            "error": None,
        }
    except Exception as e:
        return {
            "success": False,
            "rows": [],
            "row_count": 0,
            "error": str(e),
        }


def compare_results(
    full_result: Dict,
    pruned_result: Dict,
) -> str:
    """
    Helper function used to compare full-schema and
    pruned-schema query results.

    Returns match status:
      BOTH_EXACT      Both executed, identical results
      SAME_ROW_COUNT  Both executed, same row count,
                      different content
      DIFF_STRATEGY   Both executed, different row counts
                      (LLM chose a different approach)
      PRUNED_BETTER   Only pruned-schema succeeded
      FULL_BETTER     Only full-schema succeeded
      BOTH_FAIL       Neither executed successfully
    """
    if not full_result["success"] and not pruned_result["success"]:
        return "BOTH_FAIL"
    if full_result["success"] and not pruned_result["success"]:
        return "FULL_BETTER"
    if not full_result["success"] and pruned_result["success"]:
        return "PRUNED_BETTER"

    # Both succeeded — compare row counts and content
    if full_result["row_count"] != pruned_result["row_count"]:
        return "DIFF_STRATEGY"

    full_str = sorted(
        json.dumps(r, sort_keys=True, default=str)
        for r in full_result["rows"]
    )
    pruned_str = sorted(
        json.dumps(r, sort_keys=True, default=str)
        for r in pruned_result["rows"]
    )
    if full_str == pruned_str:
        return "BOTH_EXACT"
    return "SAME_ROW_COUNT"


def check_sql_pattern(
    sql: str,
    pattern: str | None,
) -> bool:
    """
    Helper function used to check whether generated SQL
    matches the expected SQL pattern from golden queries.
    """
    if not pattern:
        return True
    return bool(re.search(pattern, sql, re.IGNORECASE | re.DOTALL))


def run_e2e_validation(
    verbose: bool = False,
    query_filter: str | None = None,
) -> None:
    """
    Run end-to-end validation comparing full-schema
    vs pruned-schema SQL generation pipelines.
    """
    # Suppress pruner's per-query log lines during validation
    logging.getLogger("text_to_sql.schema_pruner").setLevel(
        logging.WARNING
    )

    run_id = generate_run_id()
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    # Load schema and build pruner
    raw_ddl = load_schema_ddl()
    pruner = SchemaPruner(raw_ddl)
    full_schema = get_schema_ddl(llm_context=True)

    golden_queries = load_golden_queries()

    # Filter to prunable queries (allowed outcome with expected tables)
    prunable = [
        gq for gq in golden_queries
        if gq["expected_outcome"] == "allowed"
        and gq["expected_tables"]
    ]

    if query_filter:
        prunable = [
            gq for gq in prunable
            if gq["id"] == query_filter
        ]
        if not prunable:
            logger.info(
                f"No prunable query found with ID: {query_filter}"
            )
            return

    logger.info(
        f"E2E validation: {len(prunable)} queries, model={model}"
    )
    logger.info("")
    logger.info(
        "  ID       Outcome          Full    Pruned  "
        "Pattern  Reduction  Latency (F/P)"
    )
    logger.info("  " + "-" * 82)

    counts = {
        "BOTH_EXACT": 0,
        "SAME_ROW_COUNT": 0,
        "DIFF_STRATEGY": 0,
        "PRUNED_BETTER": 0,
        "FULL_BETTER": 0,
        "BOTH_FAIL": 0,
    }
    full_successes = 0
    pruned_successes = 0
    full_pattern_hits = 0
    pruned_pattern_hits = 0
    reductions = []
    full_latencies = []
    pruned_latencies = []
    total_full_prompt_tokens = 0
    total_pruned_prompt_tokens = 0
    details = []

    for gq in prunable:
        query = gq["nl_query"]
        query_id = gq["id"]
        expected_pattern = gq.get("expected_sql_pattern")

        # Prune schema (needed regardless of call order)
        prune_result = pruner.prune(query, max_depth=0)

        # Randomise call order to avoid systematic
        # first-call latency bias (TCP/TLS warmup)
        full_first = random.random() < 0.5

        if full_first:
            t0 = time.monotonic()
            full_sql, full_usage = generate_sql(
                question=query,
                schema=full_schema,
                client=client,
                model=model,
            )
            full_latency = time.monotonic() - t0

            t0 = time.monotonic()
            pruned_sql, pruned_usage = generate_sql(
                question=query,
                schema=prune_result.pruned_schema,
                client=client,
                model=model,
            )
            pruned_latency = time.monotonic() - t0
        else:
            t0 = time.monotonic()
            pruned_sql, pruned_usage = generate_sql(
                question=query,
                schema=prune_result.pruned_schema,
                client=client,
                model=model,
            )
            pruned_latency = time.monotonic() - t0

            t0 = time.monotonic()
            full_sql, full_usage = generate_sql(
                question=query,
                schema=full_schema,
                client=client,
                model=model,
            )
            full_latency = time.monotonic() - t0

        total_full_prompt_tokens += full_usage.get(
            "prompt_tokens", 0
        )
        total_pruned_prompt_tokens += pruned_usage.get(
            "prompt_tokens", 0
        )

        # Execute both
        full_result = execute_sql_safe(full_sql)
        pruned_result = execute_sql_safe(pruned_sql)

        # Compare results
        outcome = compare_results(full_result, pruned_result)
        counts[outcome] += 1
        if full_result["success"]:
            full_successes += 1
        if pruned_result["success"]:
            pruned_successes += 1

        # Check SQL pattern
        full_pattern = check_sql_pattern(full_sql, expected_pattern)
        pruned_pattern = check_sql_pattern(
            pruned_sql, expected_pattern
        )
        if full_pattern:
            full_pattern_hits += 1
        if pruned_pattern:
            pruned_pattern_hits += 1

        pattern_col = (
            "F/P" if full_pattern and pruned_pattern
            else f"{'F' if full_pattern else '-'}/"
                 f"{'P' if pruned_pattern else '-'}"
        )

        reduction = prune_result.reduction_pct
        reductions.append(reduction)
        full_latencies.append(full_latency)
        pruned_latencies.append(pruned_latency)

        detail = {
            "id": query_id,
            "query": query,
            "outcome": outcome,
            "full_sql": full_sql,
            "pruned_sql": pruned_sql,
            "full_success": full_result["success"],
            "pruned_success": pruned_result["success"],
            "full_rows": full_result["row_count"],
            "pruned_rows": pruned_result["row_count"],
            "full_error": full_result["error"],
            "pruned_error": pruned_result["error"],
            "full_pattern_match": full_pattern,
            "pruned_pattern_match": pruned_pattern,
            "full_latency_s": round(full_latency, 2),
            "pruned_latency_s": round(pruned_latency, 2),
            "full_prompt_tokens": full_usage.get(
                "prompt_tokens", 0
            ),
            "pruned_prompt_tokens": pruned_usage.get(
                "prompt_tokens", 0
            ),
            "reduction_pct": reduction,
            "tables_selected": prune_result.selected_tables,
            "tables_expected": gq["expected_tables"],
        }
        details.append(detail)

        full_status = (
            f"{full_result['row_count']}r"
            if full_result["success"]
            else "ERR"
        )
        pruned_status = (
            f"{pruned_result['row_count']}r"
            if pruned_result["success"]
            else "ERR"
        )

        line = (
            f"  {query_id}  {outcome:<16} "
            f"{full_status:>6}  {pruned_status:>6}  "
            f"{pattern_col:>5}    "
            f"{reduction:5.1f}%"
            f"  {full_latency:5.2f}s/{pruned_latency:5.2f}s"
        )
        logger.info(line)

        if verbose:
            logger.info(f"         Q: {query}")
            logger.info(f"         Full SQL:   {full_sql}")
            logger.info(f"         Pruned SQL: {pruned_sql}")
            if full_result["error"]:
                logger.info(
                    f"         Full err:   "
                    f"{full_result['error'][:120]}"
                )
            if pruned_result["error"]:
                logger.info(
                    f"         Pruned err: "
                    f"{pruned_result['error'][:120]}"
                )
            logger.info("")

    if not prunable:
        return

    # Summary
    n = len(prunable)
    no_regressions = counts["FULL_BETTER"] == 0

    logger.info("")
    logger.info("  Summary")
    mean_full_lat = statistics.mean(full_latencies)
    mean_pruned_lat = statistics.mean(pruned_latencies)
    latency_delta = (
        (mean_full_lat - mean_pruned_lat) / mean_full_lat * 100
        if mean_full_lat > 0 else 0.0
    )

    logger.info("  " + "-" * 82)
    logger.info(
        f"  Queries:              {n}"
    )
    logger.info(
        f"  Full-schema exec:     "
        f"{full_successes}/{n} succeeded"
    )
    logger.info(
        f"  Pruned-schema exec:   "
        f"{pruned_successes}/{n} succeeded"
    )
    logger.info(
        f"  SQL pattern (full):   "
        f"{full_pattern_hits}/{n}"
    )
    logger.info(
        f"  SQL pattern (pruned): "
        f"{pruned_pattern_hits}/{n}"
    )
    logger.info(
        f"  Mean token reduction: "
        f"{statistics.mean(reductions):.1f}%"
    )
    logger.info(
        f"  Mean latency (full):  "
        f"{mean_full_lat:.2f}s"
    )
    logger.info(
        f"  Mean latency (pruned):"
        f" {mean_pruned_lat:.2f}s"
        f" (-{latency_delta:.1f}%)"
    )
    prompt_token_saving = (
        (total_full_prompt_tokens - total_pruned_prompt_tokens)
        / total_full_prompt_tokens * 100
        if total_full_prompt_tokens > 0 else 0.0
    )
    logger.info(
        f"  Prompt tokens (full):  "
        f"{total_full_prompt_tokens:,}"
    )
    logger.info(
        f"  Prompt tokens (pruned):"
        f" {total_pruned_prompt_tokens:,}"
        f" (-{prompt_token_saving:.1f}%)"
    )
    logger.info("")
    logger.info("  Outcome breakdown:")
    logger.info(
        f"    BOTH_EXACT:      {counts['BOTH_EXACT']:>2}  "
        f"(identical SQL results)"
    )
    logger.info(
        f"    SAME_ROW_COUNT:  {counts['SAME_ROW_COUNT']:>2}  "
        f"(same row count, different content)"
    )
    logger.info(
        f"    DIFF_STRATEGY:   {counts['DIFF_STRATEGY']:>2}  "
        f"(both succeeded, LLM chose different approach)"
    )
    logger.info(
        f"    PRUNED_BETTER:   {counts['PRUNED_BETTER']:>2}  "
        f"(pruned succeeded, full failed)"
    )
    logger.info(
        f"    FULL_BETTER:     {counts['FULL_BETTER']:>2}  "
        f"(full succeeded, pruned failed)"
    )
    logger.info(
        f"    BOTH_FAIL:       {counts['BOTH_FAIL']:>2}  "
        f"(neither succeeded)"
    )

    logger.info("")
    if no_regressions:
        logger.info(
            f"  Pruned-schema SQL executed: "
            f"{pruned_successes}/{n}. "
            f"Zero regressions vs full-schema."
        )
    else:
        logger.info(
            f"  Regressions (FULL_BETTER): "
            f"{counts['FULL_BETTER']}/{n}"
        )
        for d in details:
            if d["outcome"] == "FULL_BETTER":
                logger.info(
                    f"    {d['id']}  {d['query']}"
                )

    # Append detailed results as JSONL (one line per query)
    LOGS_DIR.mkdir(exist_ok=True)
    output_path = LOGS_DIR / "e2e_validation_results.jsonl"
    ts = datetime.now(timezone.utc).isoformat()
    with open(output_path, "a", encoding="utf-8") as f:
        for d in details:
            record = {
                **d,
                "run_id": run_id,
                "timestamp": ts,
                "model": model,
            }
            f.write(json.dumps(record, default=str) + "\n")
    logger.info(
        f"\n  Results appended to: {output_path}"
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description=(
            "End-to-end validation of schema pruning "
            "for Text-to-SQL"
        )
    )
    parser.add_argument(
        "--verbose", action="store_true",
        help="Show per-query SQL and error details"
    )
    parser.add_argument(
        "--query", type=str, default=None,
        help="Run validation for a single query ID (e.g. GQ-002)"
    )
    args = parser.parse_args()

    setup_logging()
    run_e2e_validation(
        verbose=args.verbose,
        query_filter=args.query,
    )
