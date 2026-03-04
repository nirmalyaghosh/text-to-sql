"""
Agentic core demo: three foundational agents.

Demonstrates the core agents working together:
1. Query Refinement Agent (disambiguates and refines NL)
2. Security & Governance Agent (validates permissions and safety)
3. Orchestrator Agent (coordinates everything)

Run:
    uv run python -m demos.06_agentic_core
"""

import asyncio
import sys
from dotenv import load_dotenv
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from text_to_sql.agents.types import QueryRequest
from text_to_sql.agents.orchestrator import OrchestratorAgent
from text_to_sql.agents.query_refinement import QueryRefinementAgent
from text_to_sql.agents.security_governance import SecurityGovernanceAgent
from text_to_sql.app_logger import setup_logging, get_logger


logger = get_logger(__name__)


async def demo_agent_pipeline():
    """
    Demonstrate the core agent pipeline.
    """
    setup_logging()
    logger.info("Starting Agentic Core Demo")

    # Test queries with different characteristics
    test_cases = [
        {
            "name": "Simple select (analyst role)",
            "query": "Show all active products in the Electronics category",
            "user_context": {"role": "analyst", "user_id": "user123"},
        },
        {
            "name": "Query with temporal reference",
            "query": "What were total sales last month?",
            "user_context": {"role": "analyst", "user_id": "user123"},
        },
        {
            "name": "Ambiguous query",
            "query": "Show me the best products",
            "user_context": {"role": "analyst", "user_id": "user123"},
        },
        {
            "name": "PII access attempt (should be blocked)",
            "query": "Show all customer emails and phone numbers",
            "user_context": {"role": "analyst", "user_id": "user123"},
        },
        {
            "name": "Destructive query (should be blocked)",
            "query": "DELETE all customers who haven't ordered in 6 months",
            "user_context": {"role": "analyst", "user_id": "user123"},
        },
        {
            "name": "Unauthorized role (should be blocked)",
            "query": "Show sales by region",
            "user_context": {"role": "intern", "user_id": "user456"},
        },
    ]

    # Initialize agents
    logger.info("Initializing agents...")
    orchestrator = OrchestratorAgent()
    refinement_agent = QueryRefinementAgent()
    security_agent = SecurityGovernanceAgent()

    # Inject dependencies
    orchestrator.inject_agent("refinement", refinement_agent)
    orchestrator.inject_agent("security", security_agent)

    logger.info("Agents initialized. Starting test cases...\n")

    # Run test cases
    for i, test_case in enumerate(test_cases, 1):
        logger.info("")
        logger.info("=" * 80)
        logger.info(
            f"Test Case {i}: {test_case['name']}"
        )
        logger.info("=" * 80)
        logger.info(f"Query: {test_case['query']}")
        logger.info(
            f"User Role: "
            f"{test_case['user_context'].get('role')}"
        )
        logger.info("-" * 80)

        request = QueryRequest(
            natural_language=test_case["query"],
            user_context=test_case["user_context"],
        )

        response = await orchestrator.process_query(request)

        logger.info("")
        logger.info("Result:")
        logger.info(f"  Success: {response.success}")
        logger.info(
            f"  Answer: {response.formatted_answer}"
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
            chain_len = len(response.execution_chain)
            logger.info("")
            logger.info(
                f"Execution Chain ({chain_len} steps):"
            )
            for step in response.execution_chain:
                status = (
                    "[OK]"
                    if not step.veto_reason
                    else "[X]"
                )
                logger.info(
                    f"  {status} {step.agent_name}: "
                    f"{step.action} "
                    f"({step.duration_ms:.1f}ms)"
                )
                if step.veto_reason:
                    logger.info(
                        f"     Veto: {step.veto_reason}"
                    )

    logger.info("")
    logger.info("=" * 80)
    logger.info("Demo completed")


async def demo_individual_agents():
    """
    Demo individual agents in isolation
    (useful for debugging).
    """

    setup_logging()
    logger.info("Starting Individual Agent Demo")

    # Test Query Refinement Agent
    logger.info("")
    logger.info("=" * 80)
    logger.info("QUERY REFINEMENT AGENT")
    logger.info("=" * 80)

    refinement_agent = QueryRefinementAgent()
    request = QueryRequest(
        natural_language="Show me the best products last year",
        user_context={"role": "analyst"},
    )

    result = await refinement_agent.execute(request, {}, {})
    logger.info(
        f"Original: {request.natural_language}"
    )
    logger.info(
        f"Refined: {result.get('refined_query')}"
    )
    logger.info(
        f"Ambiguities: {result.get('ambiguity_flags')}"
    )

    # Test Security Agent
    logger.info("")
    logger.info("=" * 80)
    logger.info("SECURITY & GOVERNANCE AGENT")
    logger.info("=" * 80)

    security_agent = SecurityGovernanceAgent()

    logger.info("")
    logger.info("[Test 1: Safe query]")
    refined_query = (
        "SELECT * FROM products WHERE is_active = TRUE"
    )
    result = await security_agent.execute(
        QueryRequest(
            natural_language="Show active products",
            user_context={"role": "analyst"},
        ),
        {"refinement": {"refined_query": refined_query}},
        {},
    )
    logger.info(f"Allowed: {result.get('allowed')}")
    logger.info(
        f"Risk Score: {result.get('risk_score', 'N/A'):.2f}"
    )

    logger.info("")
    logger.info("[Test 2: Unauthorized role]")
    result = await security_agent.execute(
        QueryRequest(
            natural_language="Show products",
            user_context={"role": "guest"},
        ),
        {"refinement": {"refined_query": "SELECT * FROM products"}},
        {},
    )
    logger.info(f"Allowed: {result.get('allowed')}")
    logger.info(
        f"Veto Reason: {result.get('veto_reason')}"
    )

    logger.info("")
    logger.info("[Test 3: PII access attempt]")
    refined_query = "SELECT email, phone FROM customers"
    result = await security_agent.execute(
        QueryRequest(
            natural_language="Show customer emails",
            user_context={"role": "analyst"},
        ),
        {"refinement": {"refined_query": refined_query}},
        {},
    )
    logger.info(f"Allowed: {result.get('allowed')}")
    logger.info(
        f"Veto Reason: {result.get('veto_reason')}"
    )

    logger.info("")
    logger.info("[Test 4: Destructive query]")
    result = await security_agent.execute(
        QueryRequest(
            natural_language="Delete old records",
            user_context={"role": "analyst"},
        ),
        {
            "refinement": {
                "refined_query": (
                    "DELETE FROM customers WHERE "
                    "created < '2020-01-01'"
                )
            }
        },
        {},
    )
    logger.info(f"Allowed: {result.get('allowed')}")
    logger.info(
        f"Veto Reason: {result.get('veto_reason')}"
    )


if __name__ == "__main__":
    import sys

    # Load environment variables before initializing agents
    load_dotenv()

    if len(sys.argv) > 1 and sys.argv[1] == "--individual":
        asyncio.run(demo_individual_agents())
    else:
        asyncio.run(demo_agent_pipeline())
