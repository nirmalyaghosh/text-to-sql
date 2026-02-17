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

import tiktoken

from dotenv import load_dotenv
from openai import OpenAI

from text_to_sql.app_logger import get_logger, setup_logging
from text_to_sql.db import get_schema_ddl
from text_to_sql.prompts.prompts import get_prompt
from text_to_sql.usage_tracker import (
    generate_run_id,
    log_llm_request,
    log_llm_response,
)


logger = get_logger(__name__)

QUESTION = "Show all active products in the Electronics category"
ANSWER_SQL = "SELECT * FROM products WHERE is_active = TRUE " +\
             "AND category = 'Electronics';"
MODEL = "gpt-4o-mini"
SYSTEM_PROMPT = get_prompt("naive")


def analyze_token_waste_estimated():
    """
    Compare token counts using tiktoken (local estimate, no API calls).
    """
    logger.info("Mode: tiktoken estimate (no API calls)")

    enc = tiktoken.encoding_for_model(MODEL)

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

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    full_schema = get_schema_ddl(llm_context=False)
    filtered_schema = get_schema_ddl(llm_context=True)
    products_table = _extract_products_table(full_schema)

    full_usage = _call_llm(client=client, schema_text=full_schema)
    filtered_usage = _call_llm(client=client, schema_text=filtered_schema)
    ideal_usage = _call_llm(client=client, schema_text=products_table)

    _print_results(
        question_tokens=None,
        answer_tokens=full_usage["completion_tokens"],
        full_tokens=full_usage["prompt_tokens"],
        filtered_tokens=filtered_usage["prompt_tokens"],
        ideal_tokens=ideal_usage["prompt_tokens"],
    )


def _call_llm(client: OpenAI, schema_text: str) -> dict:
    """
    Send a query to the LLM and return the usage dict.
    """
    user_content = f"Schema:\n{schema_text}\n\nQuestion: {QUESTION}"
    request_id = log_llm_request(
        model=MODEL,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_content,
        question=QUESTION,
    )
    response = client.chat.completions.create(
        model=MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )
    resp_dict = response.usage.model_dump() if response.usage else {}
    log_llm_response(
        request_id=request_id,
        model=MODEL,
        question=QUESTION,
        usage=resp_dict,
        generated_sql=response.choices[0].message.content.strip(),
        trim_sql_preview=True,
    )
    return resp_dict


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
        question_tokens: int | None,
        answer_tokens: int,
        full_tokens: int,
        filtered_tokens: int,
        ideal_tokens: int):
    """
    Print the token waste comparison table.
    """
    content = []
    content.append(f"Model: {MODEL}")
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
        generate_run_id()
        analyze_token_waste_live()
    else:
        analyze_token_waste_estimated()
