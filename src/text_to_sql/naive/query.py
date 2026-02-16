"""
Naïve Text-to-SQL: prompt-and-pray approach.

Deliberately simple. No validation, no safety checks, no error handling.
The simplicity IS the point — this is what most demos show,
and it's exactly what breaks in production.
"""

import logging
import os

from dotenv import load_dotenv
from openai import OpenAI

from text_to_sql.db import execute_query, get_schema_ddl
from text_to_sql.prompts.prompts import get_prompt


load_dotenv()

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = get_prompt("naive")


def ask(question: str, verbose: bool = False) -> list[dict]:
    """
    Take a natural language question, generate SQL, execute it,
    return results.

    That's it. No validation. No safety. No guardrails.
    """
    # Step 1: Load the entire schema as context
    schema = get_schema_ddl()

    # Step 2: Ask the LLM to generate SQL
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user",
             "content": f"Schema:\n{schema}\n\nQuestion: {question}"
            },
        ],
        temperature=0,
    )
    sql = response.choices[0].message.content.strip()

    # Clean markdown fencing if the LLM wraps it
    if sql.startswith("```"):
        sql = "\n".join(sql.split("\n")[1:-1])

    if verbose:
        logger.info("Question: %s", question)
        logger.info("Generated SQL:\n%s", sql)

    # Step 3: Execute the SQL directly — no validation whatsoever
    results = execute_query(sql)

    if verbose:
        logger.info("Results (%d rows):", len(results))
        for row in results[:10]:
            logger.info("  %s", row)
        if len(results) > 10:
            logger.info("  ... and %d more rows", len(results) - 10)

    return results
