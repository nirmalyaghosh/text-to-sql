"""
Naïve Text-to-SQL: prompt-and-pray approach.

Deliberately simple. No validation, no safety checks, no error handling.
The simplicity IS the point — this is what most demos show,
and it's exactly what breaks in production.
"""

import os

from dotenv import load_dotenv
from openai import OpenAI

from text_to_sql.app_logger import get_logger
from text_to_sql.db import execute_query, get_schema_ddl
from text_to_sql.prompts.prompts import get_prompt
from text_to_sql.usage_tracker import log_llm_request, log_llm_response


load_dotenv()

logger = get_logger(__name__)

SYSTEM_PROMPT = get_prompt("naive")


def ask(
        question: str,
        verbose: bool = False,
        max_num_result_rows: int = 10) -> list[dict]:
    """
    Helper function used to take in as input a natural language question,
    use LLM to generate SQL, execute it, and then return results.

    That's it. No validation. No safety. No guardrails.
    """
    # Step 1: Load the entire schema as context
    schema = get_schema_ddl()

    # Step 2: Ask the LLM to generate SQL
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    user_content = f"Schema:\n{schema}\n\nQuestion: {question}"

    request_id = log_llm_request(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_content,
        question=question,
    )

    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_content},
        ],
        temperature=0,
    )
    sql = response.choices[0].message.content.strip()

    log_llm_response(
        request_id=request_id,
        model=model,
        question=question,
        usage=response.usage.model_dump() if response.usage else {},
        generated_sql=sql,
    )

    # Clean markdown fencing if the LLM wraps it
    if sql.startswith("```"):
        sql = "\n".join(sql.split("\n")[1:-1])

    if verbose:
        logger.info(f"Question: {question}")
        logger.info(f"Generated SQL:\n{sql}")

    # Step 3: Execute the SQL directly — no validation whatsoever
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
