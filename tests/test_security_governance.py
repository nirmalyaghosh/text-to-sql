"""
Unit tests for SecurityGovernanceAgent.

Tests RBAC, PII detection, destructive query blocking,
and risk scoring.
"""

from typing import Callable

import pytest

from text_to_sql.agents.security_governance import (
    SecurityGovernanceAgent,
)


@pytest.fixture
def agent():
    """Create a SecurityGovernanceAgent instance."""
    return SecurityGovernanceAgent()


@pytest.fixture
def agent_extended_pii():
    """
    Create a SecurityGovernanceAgent with
    extended PII patterns enabled.
    """
    return SecurityGovernanceAgent(extended_pii=True)


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
    """Safety: DELETE FROM queries are blocked."""
    query = "DELETE FROM orders WHERE id > 100"
    request = make_request(query, role="admin")
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": query,
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


# --- NL false-positive avoidance ---


@pytest.mark.asyncio
async def test_nl_create_no_false_positive(
    agent: SecurityGovernanceAgent,
    make_request: Callable,
):
    """
    Safety: NL 'create' (e.g. 'created date')
    must not trigger a false positive.
    """
    query = "Show created date for each order"
    request = make_request(query, role="analyst")
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": query,
            },
        },
        context={},
    )
    assert result.get("allowed") is True


@pytest.mark.asyncio
async def test_nl_drop_no_false_positive(
    agent: SecurityGovernanceAgent,
    make_request: Callable,
):
    """
    Safety: NL 'drop' (e.g. 'drop in revenue')
    must not trigger a false positive.
    """
    query = "Show the biggest drop in revenue"
    request = make_request(query, role="analyst")
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": query,
            },
        },
        context={},
    )
    assert result.get("allowed") is True


@pytest.mark.asyncio
async def test_nl_update_no_false_positive(
    agent: SecurityGovernanceAgent,
    make_request: Callable,
):
    """
    Safety: NL 'update' (e.g. 'latest update')
    must not trigger a false positive.
    """
    query = "Show me the latest update"
    request = make_request(query, role="analyst")
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": query,
            },
        },
        context={},
    )
    assert result.get("allowed") is True


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
async def test_risk_nl_join_no_false_positive(agent):
    """
    Risk: NL 'join' (e.g. 'join date') does
    not inflate the risk score.
    """
    score = await agent._assess_risk(
        "Show join date of employees"
    )
    assert score == 0.0


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


@pytest.mark.asyncio
async def test_risk_score_simple_query(agent):
    """Risk: simple query has low risk score."""
    score = await agent._assess_risk(
        "SELECT * FROM products"
    )
    assert 0.0 <= score <= 0.3


# --- Extended PII (national ID) ---


@pytest.mark.asyncio
async def test_pii_nric_allowed_when_not_extended(
    agent, make_request,
):
    """
    PII: NRIC not blocked when extended_pii
    is False (default).
    """
    request = make_request(
        "Show customer NRIC numbers",
        role="analyst",
    )
    result = await agent.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show customer NRIC numbers"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is True


@pytest.mark.asyncio
async def test_pii_nric_blocked_when_extended(
    agent_extended_pii, make_request,
):
    """
    PII: NRIC blocked when extended_pii is True.
    """
    request = make_request(
        "Show customer NRIC numbers",
        role="analyst",
    )
    result = await agent_extended_pii.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show customer NRIC numbers"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


@pytest.mark.asyncio
async def test_pii_aadhaar_blocked_when_extended(
    agent_extended_pii, make_request,
):
    """
    PII: Aadhaar blocked when extended_pii
    is True.
    """
    request = make_request(
        "Show customer aadhaar numbers",
        role="analyst",
    )
    result = await agent_extended_pii.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show customer aadhaar numbers"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False


# --- Post-generation SQL audit ---


@pytest.mark.asyncio
async def test_audit_blocks_delete(agent):
    """Audit: DELETE FROM is blocked."""
    result = await agent.audit_generated_sql(
        "DELETE FROM orders WHERE id > 100"
    )
    assert result.get("safe") is False


@pytest.mark.asyncio
async def test_audit_blocks_drop(agent):
    """Audit: DROP TABLE is blocked."""
    result = await agent.audit_generated_sql(
        "DROP TABLE customers"
    )
    assert result.get("safe") is False


@pytest.mark.asyncio
async def test_audit_blocks_insert(agent):
    """Audit: INSERT INTO is blocked."""
    result = await agent.audit_generated_sql(
        "INSERT INTO orders VALUES (1, 'test')"
    )
    assert result.get("safe") is False


@pytest.mark.asyncio
async def test_audit_blocks_update(agent):
    """Audit: UPDATE...SET is blocked."""
    result = await agent.audit_generated_sql(
        "UPDATE orders SET status = 'cancelled'"
    )
    assert result.get("safe") is False


@pytest.mark.asyncio
async def test_audit_nric_blocked_with_extended(
    agent_extended_pii,
):
    """
    Audit: NRIC blocked when extended_pii is True.
    """
    result = await agent_extended_pii.audit_generated_sql(
        sql="SELECT nric FROM customers",
        user_role="analyst",
    )
    assert result.get("safe") is False
    assert "PII" in result.get("reason", "")


@pytest.mark.asyncio
async def test_audit_nric_passes_without_extended(agent):
    """
    Audit: NRIC not flagged when extended_pii is
    False (default).
    """
    result = await agent.audit_generated_sql(
        sql="SELECT nric FROM customers",
        user_role="analyst",
    )
    assert result.get("safe") is True


@pytest.mark.asyncio
async def test_audit_pii_allowed_for_admin(agent):
    """Audit: admin CAN get PII via generated SQL."""
    result = await agent.audit_generated_sql(
        sql="SELECT email FROM customers",
        user_role="admin",
    )
    assert result.get("safe") is True


@pytest.mark.asyncio
async def test_audit_pii_blocked_for_analyst(agent):
    """Audit: analyst cannot get PII via generated SQL."""
    result = await agent.audit_generated_sql(
        sql="SELECT email FROM customers",
        user_role="analyst",
    )
    assert result.get("safe") is False
    assert "PII" in result.get("reason", "")


@pytest.mark.asyncio
async def test_audit_safe_select(agent):
    """Audit: safe SELECT passes."""
    result = await agent.audit_generated_sql(
        "SELECT COUNT(*) FROM orders"
    )
    assert result.get("safe") is True


@pytest.mark.asyncio
async def test_pii_chinese_id_blocked_when_extended(
    agent_extended_pii, make_request,
):
    """
    PII: Chinese national ID (身份证号) blocked
    when extended_pii is True.
    """
    request = make_request(
        "Show customer 身份证号",
        role="analyst",
    )
    result = await agent_extended_pii.execute(
        request=request,
        previous_results={
            "refinement": {
                "refined_query": (
                    "Show customer 身份证号"
                ),
            },
        },
        context={},
    )
    assert result.get("allowed") is False
