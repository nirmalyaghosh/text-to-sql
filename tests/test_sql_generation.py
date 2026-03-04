"""
Unit tests for SQLGenerationAgent.

Tests syntax validation and error handling.
LLM-dependent tests are marked for integration runs.
"""

import pytest

from text_to_sql.agents.sql_generation import (
    SQLGenerationAgent,
)


@pytest.fixture
def agent():
    """Create SQLGenerationAgent instance."""
    return SQLGenerationAgent()


class TestSyntaxValidation:
    """Tests for deterministic SQL syntax checks."""

    def test_valid_select(self, agent):
        """Syntax: valid SELECT passes."""
        sql = (
            "SELECT COUNT(*) FROM orders "
            "WHERE order_date > '2026-01-01'"
        )
        is_valid, issues = agent._validate_syntax(
            sql
        )
        assert is_valid is True
        assert issues == []

    def test_delete_rejected(self, agent):
        """Syntax: DELETE is rejected."""
        sql = "DELETE FROM orders WHERE id = 1"
        is_valid, issues = agent._validate_syntax(
            sql
        )
        assert is_valid is False
        assert any(
            "DELETE" in i for i in issues
        )

    def test_drop_rejected(self, agent):
        """Syntax: DROP is rejected."""
        sql = "DROP TABLE orders"
        is_valid, issues = agent._validate_syntax(
            sql
        )
        assert is_valid is False

    def test_missing_from(self, agent):
        """Syntax: missing FROM is flagged."""
        sql = "SELECT 1 + 1"
        is_valid, issues = agent._validate_syntax(
            sql
        )
        assert is_valid is False
        assert any(
            "FROM" in i for i in issues
        )

    def test_unbalanced_parens(self, agent):
        """Syntax: unbalanced parens flagged."""
        sql = (
            "SELECT COUNT(*) FROM orders "
            "WHERE (status = 'active'"
        )
        is_valid, issues = agent._validate_syntax(
            sql
        )
        assert is_valid is False
        assert any(
            "parentheses" in i.lower()
            for i in issues
        )

    def test_complex_valid_query(self, agent):
        """Syntax: complex JOIN query passes."""
        sql = (
            "SELECT p.product_name, "
            "SUM(oi.total_price) AS revenue "
            "FROM products p "
            "JOIN order_items oi "
            "ON p.product_id = oi.product_id "
            "GROUP BY p.product_name "
            "ORDER BY revenue DESC"
        )
        is_valid, issues = agent._validate_syntax(
            sql
        )
        assert is_valid is True

    def test_insert_rejected(self, agent):
        """Syntax: INSERT is rejected."""
        sql = (
            "INSERT INTO orders (customer_id) "
            "VALUES (1)"
        )
        is_valid, issues = agent._validate_syntax(
            sql
        )
        assert is_valid is False

    def test_update_rejected(self, agent):
        """Syntax: UPDATE is rejected."""
        sql = (
            "UPDATE orders SET status = 'closed' "
            "WHERE id = 1"
        )
        is_valid, issues = agent._validate_syntax(
            sql
        )
        assert is_valid is False


    def test_truncate_rejected(self, agent):
        """Syntax: TRUNCATE is rejected."""
        sql = "TRUNCATE TABLE orders"
        is_valid, issues = agent._validate_syntax(
            sql
        )
        assert is_valid is False

    def test_alter_rejected(self, agent):
        """Syntax: ALTER is rejected."""
        sql = (
            "ALTER TABLE orders "
            "ADD COLUMN x INT"
        )
        is_valid, issues = agent._validate_syntax(
            sql
        )
        assert is_valid is False


class TestErrorHandling:
    """Tests for error result building."""

    def test_error_result_structure(self, agent):
        """Error: result has expected keys."""
        import time
        result = agent._build_error_result(
            "test error", time.time()
        )
        assert result["final_sql"] is None
        assert result["confidence_score"] == 0.0
        assert result["error"] == "test error"
        assert "execution_step" in result


class TestGenerationInputs:
    """Tests for input extraction from pipeline."""

    def test_extracts_from_previous(
        self, agent, make_request,
    ):
        """Inputs: extracts query, schema, tables."""
        request = make_request("Show orders")
        previous = {
            "refinement": {
                "refined_query": "Show all orders",
            },
            "schema": {
                "pruned_schema": "CREATE TABLE ...",
                "selected_tables": ["orders"],
            },
        }
        query, schema, tables = (
            agent._get_generation_inputs(
                request, previous
            )
        )
        assert query == "Show all orders"
        assert schema == "CREATE TABLE ..."
        assert tables == ["orders"]

    def test_falls_back_to_original(
        self, agent, make_request,
    ):
        """Inputs: uses original when no refinement."""
        request = make_request("Show orders")
        query, schema, tables = (
            agent._get_generation_inputs(
                request, {}
            )
        )
        assert query == "Show orders"
        assert schema == ""
        assert tables == []


class TestRecord:
    """Tests for critique history recording."""

    def test_record_appends_entry(self):
        """Record: appends entry to history list."""
        history = []
        SQLGenerationAgent._record(
            history, 1, "SELECT 1",
            "No issues", "accepted",
        )
        assert len(history) == 1
        assert history[0]["attempt"] == 1
        assert history[0]["sql"] == "SELECT 1"
        assert history[0]["action"] == "accepted"

    def test_record_multiple_entries(self):
        """Record: multiple entries accumulate."""
        history = []
        SQLGenerationAgent._record(
            history, 1, "SELECT 1",
            "Issues found", "retry",
        )
        SQLGenerationAgent._record(
            history, 2, "SELECT 2",
            "No issues", "accepted",
        )
        assert len(history) == 2
        assert history[1]["attempt"] == 2
