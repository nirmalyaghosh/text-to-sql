"""
Demo: Naïve Text-to-SQL -- success cases and failure modes.

Usage:
    python demos/01_naive_demo.py                     # run all
    python demos/01_naive_demo.py S01 S02 F01         # run specific scenarios
    python demos/01_naive_demo.py --section success   # run all in a section
    python demos/01_naive_demo.py --list              # list scenario IDs

This script demonstrates the naïve prompt-and-pray approach to Text-to-SQL
and systematically shows where it breaks on an enterprise schema.
"""

import argparse
import json
import os

from pathlib import Path

import tiktoken

from dotenv import load_dotenv
from openai import OpenAI

from text_to_sql.app_logger import get_logger, setup_logging
from text_to_sql.db import execute_query, get_schema_ddl
from text_to_sql.naive.query import ask
from text_to_sql.prompts.prompts import get_prompt
from text_to_sql.usage_tracker import generate_run_id


DIVIDER = "=" * 70
SCENARIOS_PATH = Path(__file__).parent / "scenarios.json"

logger = get_logger(__name__)


def demo_generate_only(label: str, question: str):
    """
    Generate SQL without executing -- for destructive query demos.
    """
    logger.info("\n--- %s ---", label)
    schema = get_schema_ddl()
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    model = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system",
             "content": get_prompt("naive")},
            {"role": "user",
             "content": f"Schema:\n{schema}\n\nQuestion: {question}"},
        ],
        temperature=0,
    )
    sql = response.choices[0].message.content.strip()
    if sql.startswith("```"):
        sql = "\n".join(sql.split("\n")[1:-1])
    logger.info("  Question: %s", question)
    logger.info("  Generated SQL: %s", sql)
    logger.info("  ** This would execute if we called execute_query() **")


def demo_query(label: str, question: str):
    """Run a query and display results."""
    logger.info("\n--- %s ---", label)
    try:
        results = ask(question, verbose=True)
        return results
    except Exception as e:
        logger.error("  ERROR: %s: %s", type(e).__name__, e)
        return None


def filter_scenarios(
        sections: list[dict],
        ids: list[str] | None,
        section_id: str | None) -> list[dict]:
    """
    Filter sections/scenarios based on CLI args.
    Returns filtered sections.
    """
    if not ids and not section_id:
        return sections

    if section_id:
        return [s for s in sections if s["id"] == section_id]

    # Filter by specific scenario IDs
    id_set = set(ids)
    filtered = []
    for sec in sections:
        matching = [sc for sc in sec["scenarios"] if sc["id"] in id_set]
        if matching:
            filtered.append({**sec, "scenarios": matching})
    return filtered


def list_scenarios(sections: list[dict]):
    """
    Print all scenario IDs and labels.
    """
    for sec in sections:
        logger.info("\n[%s] %s", sec["id"], sec["title"])
        for sc in sec["scenarios"]:
            mode_tag = " (generate only)" \
                if sc["mode"] == "generate_only" else ""
            logger.info("  %-5s %s%s", sc["id"], sc["label"], mode_tag)


def load_scenarios(path: Path) -> list[dict]:
    """Load scenario definitions from JSON."""
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data["sections"]


def run_context_window_cost(model: str = "gpt-4o-mini"):
    """
    Show context window cost analysis (not a scenario -- computed).
    """
    section("FAILURE MODE 5: Context Window Cost")

    schema_text = get_schema_ddl()
    enc = tiktoken.encoding_for_model(model_name=model)
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
    logger.info("And this is only 35 tables."
                "Enterprise systems have 200-500+ tables.")


def run_scenario(scenario: dict):
    """Run a single scenario based on its mode."""
    if scenario["mode"] == "execute":
        demo_query(scenario["label"], scenario["question"])
    elif scenario["mode"] == "generate_only":
        demo_generate_only(scenario["label"], scenario["question"])

    if scenario.get("remarks"):
        logger.info("  %s", scenario["remarks"])


def run_setup():
    """Show schema overview."""
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


def section(title: str):
    """Print a section header."""
    logger.info("\n%s", DIVIDER)
    logger.info("  %s", title)
    logger.info("%s", DIVIDER)


# ============================================
# MAIN
# ============================================

if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Naïve Text-to-SQL demo with selective scenario execution"
    )
    parser.add_argument(
        "scenarios", nargs="*",
        help="Scenario IDs to run (e.g. S01 F01). Omit to run all."
    )
    parser.add_argument(
        "--section", dest="section_id",
        help="Run all scenarios in a section (e.g. success, fm1_silent_wrong)"
    )
    parser.add_argument(
        "--list", action="store_true",
        help="List all scenario IDs and exit"
    )
    args = parser.parse_args()

    load_dotenv()
    setup_logging()

    sections = load_scenarios(SCENARIOS_PATH)

    if args.list:
        list_scenarios(sections)
        raise SystemExit(0)

    generate_run_id()
    running_all = not args.scenarios and not args.section_id
    filtered = filter_scenarios(sections, args.scenarios, args.section_id)

    run_setup()

    for sec in filtered:
        section(sec["title"])
        if sec.get("preamble"):
            logger.info("%s", sec["preamble"])
        for scenario in sec["scenarios"]:
            run_scenario(scenario)

    if running_all:
        run_context_window_cost()
