"""
Demo: Token waste analysis for the naïve Text-to-SQL approach.

Usage:
    python demos/02_token_waste_analysis.py            # tiktoken estimate
    python demos/02_token_waste_analysis.py --live     # actual LLM API calls

Shows how many tokens the naïve approach wastes by sending the full
schema DDL versus only the CREATE TABLE blocks, versus only the
single table actually needed for a simple query.

Use scenario S01 ("Show all active products in the Electronics category")
as the example — the simplest possible query makes the waste most visible.
"""

import argparse
import os
import re

from pathlib import Path

import tiktoken

from dotenv import load_dotenv
from llm_router_ledger import (
    get_model_name,
    send_message,
    UsageTracker,
)

from text_to_sql.app_logger import get_logger, setup_logging
from text_to_sql.db import get_schema_ddl
from text_to_sql.prompts.prompts import get_prompt


logger = get_logger(__name__)

QUESTION = "Show all active products in the Electronics category"
ANSWER_SQL = "SELECT * FROM products WHERE is_active = TRUE " +\
             "AND category = 'Electronics';"
DEFAULT_ENDPOINT = os.getenv("NAIVE_ENDPOINT", "openrouter-gpt4.1-nano")
TIKTOKEN_MODEL = "gpt-4o"  # same o200k_base tokeniser as gpt-4.1-nano
LOG_DIR = os.getenv("LOG_FILES_DIR_PATH", "logs")
LOG_FILE = os.getenv("USAGE_LOG_FILE_NAME", "token_usage.jsonl")
PROJECT_ID = "text-to-sql-naive"
SYSTEM_PROMPT = get_prompt("naive")


def analyze_token_waste_estimated():
    """
    Compare token counts using tiktoken (local estimate, no API calls).
    """
    logger.info("Mode: tiktoken estimate (no API calls)")

    enc = tiktoken.encoding_for_model(TIKTOKEN_MODEL)

    full_schema = get_schema_ddl(llm_context=False)
    filtered_schema = get_schema_ddl(llm_context=True)
    products_table = _extract_products_table(full_schema)

    full_prompt = f"Schema:\n{full_schema}\n\nQuestion: {QUESTION}"
    filtered_prompt = f"Schema:\n{filtered_schema}\n\nQuestion: {QUESTION}"
    ideal_prompt = f"Schema:\n{products_table}\n\nQuestion: {QUESTION}"

    full_tokens = len(enc.encode(full_prompt))
    filtered_tokens = len(enc.encode(filtered_prompt))
    ideal_tokens = len(enc.encode(ideal_prompt))
    question_tokens = len(enc.encode(QUESTION))
    answer_tokens = len(enc.encode(ANSWER_SQL))

    _print_results(
        model_label=f"{TIKTOKEN_MODEL} (tokeniser only)",
        question_tokens=question_tokens,
        answer_tokens=answer_tokens,
        full_tokens=full_tokens,
        filtered_tokens=filtered_tokens,
        ideal_tokens=ideal_tokens,
    )


def analyze_token_waste_live():
    """
    Compare token counts using actual LLM API calls.
    """
    logger.info("Mode: live API calls")
    logger.info("")

    full_schema = get_schema_ddl(llm_context=False)
    filtered_schema = get_schema_ddl(llm_context=True)
    products_table = _extract_products_table(full_schema)

    log_path = Path(LOG_DIR) / LOG_FILE
    with UsageTracker(
            log_path=log_path,
            project_id=PROJECT_ID) as tracker:
        full_usage = _call_llm(
            schema_text=full_schema,
            tracker=tracker,
            variant="full")
        filtered_usage = _call_llm(
            schema_text=filtered_schema,
            tracker=tracker,
            variant="filtered")
        ideal_usage = _call_llm(
            schema_text=products_table,
            tracker=tracker,
            variant="ideal")

    _print_results(
        model_label=get_model_name(DEFAULT_ENDPOINT),
        question_tokens=None,
        answer_tokens=full_usage["completion_tokens"],
        full_tokens=full_usage["prompt_tokens"],
        filtered_tokens=filtered_usage["prompt_tokens"],
        ideal_tokens=ideal_usage["prompt_tokens"],
    )


def _call_llm(
        schema_text: str,
        tracker: UsageTracker,
        variant: str) -> dict:
    """
    Send a query to the LLM and return the usage dict.
    """
    user_content = f"Schema:\n{schema_text}\n\nQuestion: {QUESTION}"
    _, usage, _ = send_message(
        endpoint_name=DEFAULT_ENDPOINT,
        system=SYSTEM_PROMPT,
        user=user_content,
        tracker=tracker,
        purpose="naive_token_waste",
        metadata={
            "question": QUESTION,
            "schema_variant": variant,
        },
        temperature=0.0,
    )
    return usage


def _extract_products_table(full_schema: str) -> str:
    """
    Extract only the CREATE TABLE products block from the full schema.
    """
    match = re.search(
        r"(CREATE TABLE products\b.*?\);)",
        full_schema,
        re.DOTALL,
    )
    return match.group(1) if match else ""


def _print_results(
        *,
        model_label: str,
        question_tokens: int | None,
        answer_tokens: int,
        full_tokens: int,
        filtered_tokens: int,
        ideal_tokens: int):
    """
    Print the token waste comparison table.
    """
    content = []
    content.append(f"Model: {model_label}")
    content.append(f"Question: {QUESTION}")
    content.append(f"Answer SQL: {ANSWER_SQL}")
    content.append("")
    if question_tokens is not None:
        content.append(f"Question tokens:              {question_tokens:>5,}")
    content.append(f"Answer SQL tokens:            {answer_tokens:>5,}")
    content.append("")
    content.append(f"Full schema prompt:           {full_tokens:>5,} tokens")
    calculation_1 = 100 - filtered_tokens / full_tokens * 100
    content.append(f"CREATE TABLE only prompt:     {filtered_tokens:>5,} tokens"
                   f"  ({calculation_1:.0f}% less)")
    content.append(f"Ideal (products table only):  {ideal_tokens:>5,} tokens"
                   f"  ({100 - ideal_tokens / full_tokens * 100:.0f}% less)")
    content.append("")
    ratio_full = full_tokens / answer_tokens
    ratio_ideal = ideal_tokens / answer_tokens
    content.append(f"Ratio (full schema : answer): {ratio_full:.0f}x")
    content.append(f"Ratio (ideal : answer):       {ratio_ideal:.0f}x")
    logger.info("Waste comparison: {}".format("\n".join(content)))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Token waste analysis for naïve Text-to-SQL"
    )
    parser.add_argument(
        "--live", action="store_true",
        help="Use actual LLM API calls instead of tiktoken estimates"
    )
    args = parser.parse_args()

    load_dotenv()
    setup_logging()

    if args.live:
        analyze_token_waste_live()
    else:
        analyze_token_waste_estimated()
