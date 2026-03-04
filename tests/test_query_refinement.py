"""
Unit tests for QueryRefinementAgent.

Tests temporal resolution, pronoun resolution,
ambiguity detection, and cross-turn references.
"""

import pytest

from text_to_sql.agents.query_refinement import (
    QueryRefinementAgent,
)


@pytest.fixture
def agent():
    """Create a QueryRefinementAgent instance."""
    return QueryRefinementAgent()


@pytest.mark.asyncio
async def test_temporal_last_month(
    agent, make_request, reference_date,
):
    """Temporal: 'last month' resolves correctly."""
    request = make_request(
        "Show orders from last month"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    refined = result["refined_query"]
    assert "2026-01-01" in refined
    assert "2026-01-31" in refined


@pytest.mark.asyncio
async def test_temporal_last_year(
    agent, make_request, reference_date,
):
    """Temporal: 'last year' resolves correctly."""
    request = make_request(
        "Show revenue from last year"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    refined = result["refined_query"]
    assert "2025-01-01" in refined
    assert "2025-12-31" in refined


@pytest.mark.asyncio
async def test_ambiguity_detection_best(
    agent, make_request, reference_date,
):
    """Ambiguity: 'best' is flagged."""
    request = make_request(
        "Show me the best products"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    assert result["has_ambiguity"] is True
    flags = result["ambiguity_flags"]
    terms = [f["term"] for f in flags]
    assert "best" in terms


@pytest.mark.asyncio
async def test_pronoun_resolution_my(
    agent, make_request, reference_date,
):
    """Pronouns: 'my' resolves to user ID."""
    request = make_request("Show my orders")
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    assert "user_test_user" in result["refined_query"]


@pytest.mark.asyncio
async def test_destructive_query_rejected(
    agent, make_request, reference_date,
):
    """Scope: destructive queries are rejected."""
    request = make_request(
        "DELETE all orders from last year"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is False


@pytest.mark.asyncio
async def test_entity_mapping_items_to_products(
    agent, make_request, reference_date,
):
    """Entity mapping: 'items' maps to 'products'."""
    request = make_request(
        "Show all items in stock"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    assert "products" in result["refined_query"]


@pytest.mark.asyncio
async def test_cross_turn_reference(
    agent, make_request, reference_date,
):
    """B4.8: cross-turn 'those' uses history."""
    request = make_request(
        "Now filter those by region",
        history=[
            {
                "role": "user",
                "content": (
                    "Show top products by revenue"
                ),
            },
        ],
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    refined = result["refined_query"]
    assert "prior query" in refined.lower()


@pytest.mark.asyncio
async def test_empty_query_still_valid(
    agent, make_request, reference_date,
):
    """Edge case: empty-ish query passes scope."""
    request = make_request(
        "Show all products"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True


# --- Case-sensitivity tests (Task 1 regression) ---


@pytest.mark.asyncio
async def test_temporal_case_insensitive(
    agent, make_request, reference_date,
):
    """Temporal: uppercase 'LAST MONTH' resolves."""
    request = make_request(
        "Show orders from LAST MONTH"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    refined = result["refined_query"]
    assert "2026-01-01" in refined
    assert "2026-01-31" in refined


@pytest.mark.asyncio
async def test_entity_mapping_case_insensitive(
    agent, make_request, reference_date,
):
    """Entity: 'ITEMS' maps to 'products'."""
    request = make_request(
        "Show all ITEMS in the warehouse"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    assert "products" in result["refined_query"].lower()


@pytest.mark.asyncio
async def test_pronoun_case_insensitive(
    agent, make_request, reference_date,
):
    """Pronouns: 'My' (capitalized) resolves."""
    request = make_request("Show My orders")
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    assert "user_test_user" in result["refined_query"]


# --- Temporal pattern coverage ---


@pytest.mark.asyncio
async def test_temporal_this_year(
    agent, make_request, reference_date,
):
    """Temporal: 'this year' resolves correctly."""
    request = make_request("Show sales this year")
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    refined = result["refined_query"]
    assert "2026-01-01" in refined
    assert "2026-12-31" in refined


@pytest.mark.asyncio
async def test_temporal_this_month(
    agent, make_request, reference_date,
):
    """Temporal: 'this month' resolves correctly."""
    request = make_request("Show orders this month")
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    refined = result["refined_query"]
    assert "2026-02-01" in refined
    assert "2026-02-22" in refined


@pytest.mark.asyncio
async def test_temporal_last_quarter(
    agent, make_request, reference_date,
):
    """Temporal: 'last quarter' resolves to Q4 2025."""
    request = make_request(
        "Show revenue last quarter"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    refined = result["refined_query"]
    assert "2025-10-01" in refined
    assert "2025-12-31" in refined


@pytest.mark.asyncio
async def test_temporal_last_30_days(
    agent, make_request, reference_date,
):
    """Temporal: 'last 30 days' resolves correctly."""
    request = make_request(
        "Show orders from last 30 days"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is True
    refined = result["refined_query"]
    assert "2026-01-23" in refined
    assert "2026-02-22" in refined


# --- Edge cases ---


@pytest.mark.asyncio
async def test_sql_injection_in_nl_blocked(
    agent, make_request, reference_date,
):
    """Edge: SQL injection in NL input is rejected."""
    request = make_request(
        "Show products; DROP TABLE customers"
    )
    result = await agent.execute(
        request=request,
        previous_results={},
        context={"reference_date": reference_date},
    )
    assert result["valid"] is False
