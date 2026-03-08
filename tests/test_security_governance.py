"""
Unit tests for SecurityGovernanceAgent.

Tests RBAC, PII detection, destructive query blocking,
and risk scoring.
"""

import pytest

from text_to_sql.agents.security_governance import (
    SecurityGovernanceAgent,
)


@pytest.fixture
def agent():
    """Create a SecurityGovernanceAgent instance."""
    return SecurityGovernanceAgent()


@pytest.mark.asyncio
async def test_analyst_allowed_simple_select(
    agent, make_request,
):
    """RBAC: analyst can run simple SELECT."""
    request = make_request(
        "Show total orders by month",
        role="analyst",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show total orders by month"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is True


@pytest.mark.asyncio
async def test_unauthorized_role_blocked(
    agent, make_request,
):
    """RBAC: unknown role is blocked."""
    request = make_request(
        "Show all orders", role="intern"
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": "Show all orders",
            },
        },
        context={},
    )
    assert result.get("allowed") is False
    assert result.get("veto_reason") is not None


@pytest.mark.asyncio
async def test_pii_email_blocked_for_analyst(
    agent, make_request,
):
    """PII: analyst cannot access customer emails."""
    request = make_request(
        "Show all customer emails",
        role="analyst",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show all customer emails"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


@pytest.mark.asyncio
async def test_pii_phone_blocked_for_analyst(
    agent, make_request,
):
    """PII: analyst cannot access phone numbers."""
    request = make_request(
        "Show customer phone numbers",
        role="analyst",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show customer phone numbers"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


@pytest.mark.asyncio
async def test_pii_allowed_for_admin(
    agent, make_request,
):
    """PII: admin CAN access customer emails."""
    request = make_request(
        "Show all customer emails",
        role="admin",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show all customer emails"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is True


@pytest.mark.asyncio
async def test_destructive_delete_blocked(
    agent, make_request,
):
    """Safety: DELETE queries are blocked."""
    request = make_request(
        "DELETE all old orders",
        role="admin",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "DELETE all old orders"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


@pytest.mark.asyncio
async def test_destructive_drop_blocked(
    agent, make_request,
):
    """Safety: DROP queries are blocked."""
    request = make_request(
        "DROP TABLE customers",
        role="admin",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "DROP TABLE customers"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


# --- TRUNCATE and ALTER blocking ---


@pytest.mark.asyncio
async def test_destructive_truncate_blocked(
    agent, make_request,
):
    """Safety: TRUNCATE queries are blocked."""
    request = make_request(
        "TRUNCATE TABLE orders",
        role="admin",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "TRUNCATE TABLE orders"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


@pytest.mark.asyncio
async def test_destructive_alter_blocked(
    agent, make_request,
):
    """Safety: ALTER queries are blocked."""
    request = make_request(
        "ALTER TABLE orders ADD COLUMN x INT",
        role="admin",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "ALTER TABLE orders "
                    "ADD COLUMN x INT"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


# --- Additional PII patterns ---


@pytest.mark.asyncio
async def test_pii_ssn_blocked(
    agent, make_request,
):
    """PII: analyst cannot access employee SSN."""
    request = make_request(
        "Show employee ssn numbers",
        role="analyst",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show employee ssn numbers"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


@pytest.mark.asyncio
async def test_pii_salary_blocked(
    agent, make_request,
):
    """PII: analyst cannot access salary data."""
    request = make_request(
        "Show employee salary data",
        role="analyst",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show employee salary data"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


@pytest.mark.asyncio
async def test_pii_credit_card_blocked(
    agent, make_request,
):
    """PII: analyst cannot access credit cards."""
    request = make_request(
        "Show customer credit card numbers",
        role="analyst",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show customer credit card "
                    "numbers"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


# --- Risk scoring ---


@pytest.mark.asyncio
async def test_risk_score_simple_query(agent):
    """Risk: simple query has low risk score."""
    score = await agent._assess_risk(
        "SELECT * FROM products"
    )
    assert 0.0 <= score <= 0.3


@pytest.mark.asyncio
async def test_risk_score_complex_joins(agent):
    """Risk: many JOINs raise risk score."""
    sql = (
        "SELECT * FROM products "
        "JOIN order_items ON x = y "
        "JOIN orders ON a = b "
        "JOIN customers ON c = d"
    )
    score = await agent._assess_risk(sql)
    assert score > 0.1
