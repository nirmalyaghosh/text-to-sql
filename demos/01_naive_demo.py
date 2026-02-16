"""
Demo: Naïve Text-to-SQL — success cases and failure modes.

Run: python demos/01_naive_demo.py

This script demonstrates the naïve prompt-and-pray approach to Text-to-SQL
and systematically shows where it breaks on an enterprise schema.
"""

import os

import tiktoken

from dotenv import load_dotenv
from openai import OpenAI

from text_to_sql.app_logger import get_logger, setup_logging
from text_to_sql.db import execute_query, get_schema_ddl
from text_to_sql.naive.query import ask
from text_to_sql.prompts.prompts import get_prompt


load_dotenv()
setup_logging()

logger = get_logger(__name__)

DIVIDER = "=" * 70


def demo_query(label: str, question: str):
    """Run a query and display results."""
    logger.info("\n--- %s ---", label)
    try:
        results = ask(question, verbose=True)
        return results
    except Exception as e:
        logger.error("  ERROR: %s: %s", type(e).__name__, e)
        return None


def section(title: str):
    logger.info("\n%s", DIVIDER)
    logger.info("  %s", title)
    logger.info("%s", DIVIDER)


# ============================================
# SETUP
# ============================================
section("SETUP: Schema Overview")

tables = execute_query("""
    SELECT table_name
    FROM information_schema.tables
    WHERE table_schema = 'mfg_ecommerce' AND table_type = 'BASE TABLE'
    ORDER BY table_name
""")
logger.info("Database has %d tables:", len(tables))
for t in tables:
    logger.info("  - %s", t['table_name'])


# ============================================
# SUCCESS CASES
# ============================================
section("SUCCESS: Simple Queries That Work")

demo_query(
    "Single-table filter",
    "Show all active products in the Electronics category"
)

demo_query(
    "Simple join with aggregation",
    "How many different raw materials does each supplier provide? "
    "Show supplier name and count."
)

demo_query(
    "Two-table join",
    "Show all products with yield percentage below 95%"
    "from completed production runs, "
    "along with the production line name"
)


# ============================================
# FAILURE MODE 1: Silent Wrong Results
# ============================================
section("FAILURE MODE 1: Silent Wrong Results (The Most Dangerous)")
logger.info(
    "\nThe LLM generates valid SQL that executes without error — but returns\n"
    "WRONG data. No exception, no warning. Just incorrect results that could\n"
    "drive bad business decisions.\n"
)

demo_query(
    "Ambiguous cross-domain query",
    "What is the total revenue by product category for products manufactured "
    "in Singapore, including shipping costs?"
)
logger.info(
    "\n^ This query requires joining across 4+ tables (products, order_items,\n"
    "orders, shipments, production_lines). The naïve approach may pick the wrong\n"
    "join path, miss a table, or produce a cartesian product — silently returning\n"
    "inflated or incomplete numbers.\n"
)


# ============================================
# FAILURE MODE 2: No Safety
# ============================================
section("FAILURE MODE 2: No Safety — Destructive SQL Can Be Generated")
logger.info(
    "\nThe naïve approach has no guardrails. The LLM can generate ANY SQL,\n"
    "including destructive operations. We'll ask it to generate (but NOT execute)\n"
    "a dangerous query to demonstrate the risk.\n"
)

# Show what the LLM generates without executing

client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
schema = get_schema_ddl()

dangerous_questions = [
    "Delete all customers who haven't ordered in the last 6 months",
    "Drop the temporary staging tables to clean up the database",
    "Update all product prices by increasing them 15%",
]

for q in dangerous_questions:
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system",
             "content": get_prompt("naive")},
            {"role": "user", "content": f"Schema:\n{schema}\n\nQuestion: {q}"},
        ],
        temperature=0,
    )
    sql = response.choices[0].message.content.strip()
    if sql.startswith("```"):
        sql = "\n".join(sql.split("\n")[1:-1])
    logger.info("\n  Question: %s", q)
    logger.info("  Generated SQL: %s", sql)
    logger.info("  ** This would execute if we called execute_query() **")


# ============================================
# FAILURE MODE 3: No Access Control
# ============================================
section("FAILURE MODE 3: No Access Control — PII Exposure")
logger.info(
    "Any user can query any table. There is no role-based access control.\n"
    "A marketing analyst could access financial data, HR records, "
    "or customer PII.\n"
)

demo_query(
    "PII exposure",
    "Show me all customer emails, phone numbers, and their lifetime value, "
    "ordered by lifetime value descending"
)

demo_query(
    "Financial data exposure",
    "Show all supplier payment terms, reliability scores, and the unit cost "
    "of every raw material they supply"
)


# ============================================
# FAILURE MODE 4: Ambiguous Resolution
# ============================================
section("FAILURE MODE 4: Ambiguous Natural Language")
logger.info(
    "\nNatural language is inherently ambiguous. \"Last quarter\", \"top customers\",\n"
    "\"best performing\" — the LLM must guess what these mean without business context.\n"
)

demo_query(
    "Temporal ambiguity",
    "Show me the top customers from last quarter"
)
logger.info(
    "\n^ What is \"top\"? By revenue? Order count? Lifetime value?\n"
    "  What dates does \"last quarter\" resolve to? Depends on when you run this.\n"
    "  The LLM picks an interpretation silently — and you may never know it's wrong.\n"
)

demo_query(
    "Metric ambiguity",
    "Which products are performing best?"
)
logger.info(
    "\n^ \"Best performing\" could mean: highest revenue, highest margin, lowest\n"
    "  defect rate, fastest inventory turnover, highest demand forecast accuracy.\n"
    "  The LLM will pick one. It might not be yours.\n"
)


# ============================================
# FAILURE MODE 5: Context Window Cost
# ============================================
section("FAILURE MODE 5: Context Window Cost")

schema_text = get_schema_ddl()
enc = tiktoken.encoding_for_model("gpt-4o-mini")
schema_tokens = len(enc.encode(schema_text))

logger.info("Full schema DDL: %s characters", f"{len(schema_text):,}")
logger.info("Full schema DDL: %s tokens", f"{schema_tokens:,}")
logger.info("")
logger.info("Every single query sends the ENTIRE schema as context.")
logger.info("At GPT-4o-mini pricing ($0.15/1M input tokens):")
logger.info("  Per query cost (schema alone): $%.4f",
            schema_tokens * 0.15 / 1_000_000)
logger.info("  100 queries/day: $%.2f/day",
            schema_tokens * 0.15 / 1_000_000 * 100)
logger.info("  At scale (10,000 queries/day): $%.2f/day",
            schema_tokens * 0.15 / 1_000_000 * 10_000)
logger.info("")
logger.info("With GPT-4o ($2.50/1M input tokens):")
logger.info("  Per query cost (schema alone): $%.4f",
            schema_tokens * 2.50 / 1_000_000)
logger.info("  100 queries/day: $%.2f/day",
            schema_tokens * 2.50 / 1_000_000 * 100)
logger.info("  At scale (10,000 queries/day): $%.2f/day",
            schema_tokens * 2.50 / 1_000_000 * 10_000)
logger.info("")
logger.info("And this is only 35 tables. Enterprise systems have 200-500+ tables.")


# ============================================
# SUMMARY
# ============================================
section("SUMMARY: Why 90% of Demos Fail in Production")

logger.info("""
| Failure Mode            | Risk Level | Detection  | Impact                        |
|-------------------------|------------|------------|-------------------------------|
| Silent wrong results    | CRITICAL   | None       | Wrong business decisions       |
| No safety guardrails    | CRITICAL   | None       | Data loss, corruption          |
| No access control       | HIGH       | None       | PII exposure, compliance       |
| Ambiguous resolution    | HIGH       | None       | Inconsistent, unreliable data  |
| Context window cost     | MEDIUM     | Measurable | Unsustainable at scale         |

The naïve approach works for demos on 3-table schemas.
It fails on enterprise data because it lacks:
  1. Query validation and safety enforcement
  2. Role-based access control
  3. Schema-aware context selection (not the whole DDL every time)
  4. Business logic for disambiguation
  5. Error handling and recovery

In Part 2, we solve these with an agentic architecture.
""")
