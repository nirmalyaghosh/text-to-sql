"""
Naïve Text-to-SQL: prompt-and-pray approach.

Deliberately simple. No validation, no safety checks, no error handling.
The simplicity IS the point — this is what most demos show,
and it's exactly what breaks in production.

LLM dispatch and JSONL logging are delegated to llm_router_ledger.
"""

import os

from dotenv import load_dotenv

from llm_router_ledger import (
    send_message,
    UsageTracker,
)

from text_to_sql.app_logger import get_logger
from text_to_sql.db import execute_query, get_schema_ddl
from text_to_sql.prompts.prompts import get_prompt


load_dotenv()

logger = get_logger(__name__)

DEFAULT_ENDPOINT = os.getenv("NAIVE_ENDPOINT", "openrouter-gpt4.1-nano")
SYSTEM_PROMPT = get_prompt("naive")


def ask(
        question: str,
        verbose: bool = False,
        max_num_result_rows: int = 10,
        tracker: UsageTracker | None = None,
        endpoint_name: str = DEFAULT_ENDPOINT) -> list[dict]:
    """
    Helper function used to take in as input a natural language question,
    use LLM to generate SQL, execute it, and then return results.

    That's it. No validation. No safety. No guardrails.

    When tracker is provided, paired llm_request / llm_response events
    are written to its JSONL log.
    """
    schema = get_schema_ddl()
    user_content = f"Schema:\n{schema}\n\nQuestion: {question}"

    sql, _, _ = send_message(
        endpoint_name=endpoint_name,
        system=SYSTEM_PROMPT,
        user=user_content,
        tracker=tracker,
        purpose="naive",
        metadata={"question": question},
        temperature=0.0,
    )
    sql = sql.strip()

    if sql.startswith("```"):
        sql = "\n".join(sql.split("\n")[1:-1])

    if verbose:
        logger.info(f"Question: {question}")
        logger.info(f"Generated SQL:\n{sql}")

    results = execute_query(sql)

    if verbose:
        results_filtered = results[:max_num_result_rows]
        results_to_show = "".join(f"{row}\n" for row in results_filtered)
        results_to_show = results_to_show.strip() if results_to_show \
            else "  (no results)"
        logger.info(f"Results ({len(results)} rows):\n{results_to_show}")
        if len(results) > max_num_result_rows:
            num_remaining = len(results) - max_num_result_rows
            logger.info(f"  ... and {num_remaining} more rows")

    return results
