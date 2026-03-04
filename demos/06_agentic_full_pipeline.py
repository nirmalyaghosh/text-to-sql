"""
Agentic full pipeline demo.

Demonstrates all agents end-to-end:
- Schema Intelligence (FK graph + token pruning)
- SQL Generation with self-critique loop
- Provenance tracking via execution chain
- Cross-turn conversation history

Usage:
    uv run python -m demos.06_agentic_full_pipeline
"""

import asyncio
from datetime import datetime

from dotenv import load_dotenv

from text_to_sql.agents import (
    OrchestratorAgent,
    QueryRequest,
)
from text_to_sql.agents.query_refinement import (
    QueryRefinementAgent,
)
from text_to_sql.agents.schema_intelligence import (
    SchemaIntelligenceAgent,
)
from text_to_sql.agents.security_governance import (
    SecurityGovernanceAgent,
)
from text_to_sql.agents.sql_generation import (
    SQLGenerationAgent,
)
from text_to_sql.app_logger import (
    get_logger,
    setup_logging,
)


logger = get_logger(__name__)


def _log_divider():
    """
    Log a visual divider.
    """
    logger.info("=" * 60)


def _log_result(
    test_num: int,
    description: str,
    response,
):
    """
    Log formatted test result.
    """
    _log_divider()
    logger.info(f"Test {test_num}: {description}")
    _log_divider()
    logger.info(f"  Success: {response.success}")

    if response.generated_sql:
        logger.info(
            f"  SQL:\n    {response.generated_sql}"
        )
    elif response.formatted_answer:
        answer = response.formatted_answer[:200]
        logger.info(f"  Answer: {answer}")

    if response.natural_language_summary:
        logger.info(
            f"  Summary: "
            f"{response.natural_language_summary}"
        )

    if response.error_message:
        logger.info(
            f"  Error: {response.error_message}"
        )

    logger.info(
        f"  Confidence: "
        f"{response.confidence_score:.2f}"
    )

    if response.execution_chain:
        logger.info(
            f"\n  Execution Chain "
            f"({len(response.execution_chain)} "
            f"steps):"
        )
        for step in response.execution_chain:
            if step is None:
                continue
            status = (
                "[X]" if step.veto_reason else "[OK]"
            )
            logger.info(
                f"    {status} {step.agent_name}: "
                f"{step.action} "
                f"({step.duration_ms:.1f}ms)"
            )
            if step.veto_reason:
                logger.info(
                    f"       Veto: "
                    f"{step.veto_reason}"
                )
            bench = step.output_data.get(
                "tokens_before"
            )
            if bench:
                after = step.output_data.get(
                    "tokens_after", 0
                )
                pct = step.output_data.get(
                    "reduction_pct", 0
                )
                logger.info(
                    f"       Tokens: {bench} -> "
                    f"{after} ({pct}% reduction)"
                )
            attempts = step.output_data.get(
                "attempts"
            )
            if attempts:
                conf = step.output_data.get(
                    "confidence", 0
                )
                logger.info(
                    f"       Attempts: {attempts}, "
                    f"Confidence: {conf:.2f}"
                )
    logger.info("")


async def run_full_pipeline_demo():
    """
    Run the full agentic pipeline demo.
    """
    logger.info("")
    logger.info("=" * 60)
    logger.info("  Full Agentic Text-to-SQL Pipeline")
    logger.info(
        "  Schema Intelligence + SQL Generation"
    )
    logger.info("  with Self-Critique Loop")
    logger.info("=" * 60)
    logger.info("")

    # Initialize agents
    orchestrator = OrchestratorAgent()
    refinement = QueryRefinementAgent()
    security = SecurityGovernanceAgent()
    schema_intel = SchemaIntelligenceAgent()
    sql_gen = SQLGenerationAgent()

    # Inject all agents
    orchestrator.inject_agent(
        "refinement", refinement
    )
    orchestrator.inject_agent("security", security)
    orchestrator.inject_agent("schema", schema_intel)
    orchestrator.inject_agent(
        "sql_generation", sql_gen
    )

    ref_date = datetime(2026, 2, 22)
    orchestrator.set_conversation_state(
        {"reference_date": ref_date}
    )

    # ---- Test 1: Simple single-table query ----
    request1 = QueryRequest(
        natural_language=(
            "How many orders were placed last month?"
        ),
        user_context={"role": "analyst"},
    )
    response1 = await orchestrator.process_query(
        request1
    )
    _log_result(
        1,
        "Simple query (single table, temporal)",
        response1,
    )

    # ---- Test 2: Multi-table JOIN query ----
    request2 = QueryRequest(
        natural_language=(
            "Show total revenue by product category"
        ),
        user_context={"role": "analyst"},
    )
    response2 = await orchestrator.process_query(
        request2
    )
    _log_result(
        2,
        "Multi-table JOIN (revenue by category)",
        response2,
    )

    # ---- Test 3: Complex analytical query ----
    request3 = QueryRequest(
        natural_language=(
            "Which customers have the highest "
            "order frequency this year?"
        ),
        user_context={"role": "analyst"},
    )
    response3 = await orchestrator.process_query(
        request3
    )
    _log_result(
        3,
        "Complex analytical (customer frequency)",
        response3,
    )

    # ---- Test 4: PII blocked (should still block) ----
    request4 = QueryRequest(
        natural_language=(
            "Show all customer emails and phone numbers"
        ),
        user_context={"role": "analyst"},
    )
    response4 = await orchestrator.process_query(
        request4
    )
    _log_result(
        4,
        "PII access attempt (should be BLOCKED)",
        response4,
    )

    # ---- Test 5: Inventory/supply chain query ----
    request5 = QueryRequest(
        natural_language=(
            "What is the current stock level "
            "for each product in warehouse A?"
        ),
        user_context={"role": "analyst"},
    )
    response5 = await orchestrator.process_query(
        request5
    )
    _log_result(
        5,
        "Inventory query (stock levels)",
        response5,
    )

    # ---- Test 6: Destructive (should still block) ----
    request6 = QueryRequest(
        natural_language=(
            "DELETE all orders from last year"
        ),
        user_context={"role": "analyst"},
    )
    response6 = await orchestrator.process_query(
        request6
    )
    _log_result(
        6,
        "Destructive query (should be BLOCKED)",
        response6,
    )

    # ---- Test 7: Cross-turn conversation (B4.8) ----
    request7 = QueryRequest(
        natural_language=(
            "Now filter those by region"
        ),
        user_context={"role": "analyst"},
        conversation_history=[
            {
                "role": "user",
                "content": (
                    "Show top products by revenue"
                ),
            },
            {
                "role": "assistant",
                "content": (
                    "SELECT p.product_name, "
                    "SUM(oi.total_price) ..."
                ),
            },
        ],
    )
    response7 = await orchestrator.process_query(
        request7
    )
    _log_result(
        7,
        "Cross-turn reference (B4.8 context)",
        response7,
    )

    # Summary
    _log_divider()
    logger.info("  DEMO SUMMARY")
    _log_divider()
    results = [
        (1, "Simple query", response1.success),
        (2, "Multi-JOIN", response2.success),
        (3, "Complex analytical", response3.success),
        (4, "PII blocked", not response4.success),
        (5, "Inventory", response5.success),
        (6, "Destructive blocked", not response6.success),
        (7, "Cross-turn", response7.success),
    ]
    for num, desc, passed in results:
        status = "PASS" if passed else "FAIL"
        logger.info(f"  {num}. {desc}: {status}")

    passed = sum(1 for _, _, p in results if p)
    total = len(results)
    logger.info("")
    logger.info(f"  {passed}/{total} tests passed")
    logger.info("")


if __name__ == "__main__":
    setup_logging()
    load_dotenv()
    asyncio.run(run_full_pipeline_demo())
