"""
Unit tests for OrchestratorAgent.

Tests post-generation SQL audit and response assembly.
"""

import pytest

from text_to_sql.agents.orchestrator import (
    OrchestratorAgent,
)
from text_to_sql.agents.security_governance import (
    SecurityGovernanceAgent,
)


@pytest.fixture
def orchestrator():
    """
    Create OrchestratorAgent with security agent
    injected.
    """
    orch = OrchestratorAgent()
    orch.inject_agent(
        "security", SecurityGovernanceAgent()
    )
    return orch


@pytest.fixture
def safe_sql_results():
    """
    Intermediate results with safe generated SQL.
    """
    return {
        "security": {"allowed": True},
        "schema": {"token_benchmark": {}},
        "sql_generation": {
            "final_sql": (
                "SELECT COUNT(*) FROM orders"
            ),
            "confidence_score": 0.9,
            "attempt_count": 1,
        },
    }


@pytest.fixture
def destructive_sql_results():
    """
    Intermediate results with destructive SQL.
    """
    return {
        "security": {"allowed": True},
        "schema": {"token_benchmark": {}},
        "sql_generation": {
            "final_sql": (
                "DELETE FROM orders WHERE id > 100"
            ),
            "confidence_score": 0.8,
            "attempt_count": 1,
        },
    }


# --- Post-generation SQL audit ---


@pytest.mark.asyncio
async def test_post_gen_audit_blocks_delete(
    orchestrator,
    destructive_sql_results,
    make_request,
):
    """Post-gen audit: DELETE FROM is blocked."""
    request = make_request(
        "Delete old orders", role="analyst"
    )
    response = await orchestrator._assemble_response(
        intermediate_results=destructive_sql_results,
        request=request,
        team_sequence=[
            "security", "schema", "sql_generation",
        ],
        execution_chain=[],
    )
    assert response.success is False
    assert "blocked" in response.formatted_answer.lower()
    assert response.error_message is not None


@pytest.mark.asyncio
async def test_post_gen_audit_blocks_drop(
    orchestrator,
    make_request,
):
    """Post-gen audit: DROP TABLE is blocked."""
    results = {
        "security": {"allowed": True},
        "schema": {"token_benchmark": {}},
        "sql_generation": {
            "final_sql": "DROP TABLE customers",
            "confidence_score": 0.7,
            "attempt_count": 1,
        },
    }
    request = make_request(
        "Remove customers table", role="analyst"
    )
    response = await orchestrator._assemble_response(
        intermediate_results=results,
        request=request,
        team_sequence=[
            "security", "schema", "sql_generation",
        ],
        execution_chain=[],
    )
    assert response.success is False
    assert response.error_message is not None


@pytest.mark.asyncio
async def test_post_gen_audit_passes_safe_sql(
    orchestrator,
    safe_sql_results,
    make_request,
):
    """Post-gen audit: safe SELECT passes through."""
    request = make_request(
        "Count all orders", role="analyst"
    )
    response = await orchestrator._assemble_response(
        intermediate_results=safe_sql_results,
        request=request,
        team_sequence=[
            "security", "schema", "sql_generation",
        ],
        execution_chain=[],
    )
    assert response.success is True
    assert response.generated_sql == (
        "SELECT COUNT(*) FROM orders"
    )


@pytest.mark.asyncio
async def test_post_gen_audit_records_execution_step(
    orchestrator,
    destructive_sql_results,
    make_request,
):
    """
    Post-gen audit: blocked SQL records an execution
    step with veto reason.
    """
    chain = []
    request = make_request(
        "Delete orders", role="analyst"
    )
    await orchestrator._assemble_response(
        intermediate_results=destructive_sql_results,
        request=request,
        team_sequence=[
            "security", "schema", "sql_generation",
        ],
        execution_chain=chain,
    )
    assert len(chain) == 1
    assert chain[0].action == "post_gen_audit_blocked"
    assert chain[0].veto_reason is not None


@pytest.mark.asyncio
async def test_post_gen_audit_skipped_without_security(
    make_request,
):
    """
    Post-gen audit: skipped when no security agent
    is injected, i.e. SQL passes through unaudited.
    """
    orch = OrchestratorAgent()
    results = {
        "sql_generation": {
            "final_sql": "DELETE FROM orders",
            "confidence_score": 0.8,
            "attempt_count": 1,
        },
    }
    request = make_request(
        "Delete orders", role="analyst"
    )
    response = await orch._assemble_response(
        intermediate_results=results,
        request=request,
        team_sequence=["sql_generation"],
        execution_chain=[],
    )
    assert response.success is True
    assert response.generated_sql == (
        "DELETE FROM orders"
    )
