"""
Unit tests for SchemaIntelligenceAgent.

Tests FK graph construction, entity resolution,
BFS traversal, and token benchmarking.
"""

import pytest

from text_to_sql.agents.schema_intelligence import (
    SchemaIntelligenceAgent,
    _singularize,
)
from text_to_sql.agents.types import EntityExtraction


SAMPLE_DDL = """
CREATE TABLE products (
    product_id SERIAL PRIMARY KEY,
    product_name VARCHAR(100),
    category VARCHAR(50)
);

CREATE TABLE customers (
    customer_id SERIAL PRIMARY KEY,
    name VARCHAR(100),
    email VARCHAR(200)
);

CREATE TABLE orders (
    order_id SERIAL PRIMARY KEY,
    customer_id INTEGER,
    order_date DATE,
    FOREIGN KEY (customer_id)
        REFERENCES customers(customer_id)
);

CREATE TABLE order_items (
    item_id SERIAL PRIMARY KEY,
    order_id INTEGER,
    product_id INTEGER,
    quantity INTEGER,
    total_price NUMERIC(12,2),
    FOREIGN KEY (order_id)
        REFERENCES orders(order_id),
    FOREIGN KEY (product_id)
        REFERENCES products(product_id)
);
"""


@pytest.fixture
def agent():
    """Create SchemaIntelligenceAgent instance."""
    return SchemaIntelligenceAgent()


class TestFKGraph:
    """Tests for FK graph construction."""

    def test_build_fk_graph_tables(self, agent):
        """Graph: all tables are discovered."""
        agent._build_fk_graph(SAMPLE_DDL)
        assert "products" in agent._all_tables
        assert "customers" in agent._all_tables
        assert "orders" in agent._all_tables
        assert "order_items" in agent._all_tables
        assert len(agent._all_tables) == 4

    def test_build_fk_graph_edges(self, agent):
        """Graph: FK edges are bidirectional."""
        agent._build_fk_graph(SAMPLE_DDL)
        # orders -> customers
        assert "customers" in agent._fk_graph["orders"]
        # customers -> orders (bidirectional)
        assert "orders" in agent._fk_graph["customers"]
        # order_items -> products
        assert (
            "products" in agent._fk_graph["order_items"]
        )

    def test_build_fk_graph_details(self, agent):
        """Graph: FK details include column info."""
        agent._build_fk_graph(SAMPLE_DDL)
        assert len(agent._fk_details) == 3
        fk_froms = [
            d["from"] for d in agent._fk_details
        ]
        assert "orders" in fk_froms
        assert "order_items" in fk_froms


class TestBFSTraversal:
    """Tests for minimal table set selection."""

    def test_single_seed(self, agent):
        """BFS: single seed finds connected tables."""
        agent._build_fk_graph(SAMPLE_DDL)
        result = agent._find_minimal_tables(
            {"orders"}, max_depth=1
        )
        assert "orders" in result
        assert "customers" in result

    def test_depth_limiting(self, agent):
        """BFS: depth=0 returns only seed."""
        agent._build_fk_graph(SAMPLE_DDL)
        result = agent._find_minimal_tables(
            {"orders"}, max_depth=0
        )
        assert result == {"orders"}

    def test_multi_seed(self, agent):
        """BFS: multiple seeds expand correctly."""
        agent._build_fk_graph(SAMPLE_DDL)
        result = agent._find_minimal_tables(
            {"products", "customers"}, max_depth=1
        )
        assert "products" in result
        assert "customers" in result
        assert "order_items" in result
        assert "orders" in result

    def test_empty_seeds(self, agent):
        """BFS: empty seeds return empty set."""
        agent._build_fk_graph(SAMPLE_DDL)
        result = agent._find_minimal_tables(
            set(), max_depth=2
        )
        assert result == set()


class TestSchemaPruning:
    """Tests for schema pruning."""

    def test_prune_selected_only(self, agent):
        """Pruning: only selected tables included."""
        agent._build_fk_graph(SAMPLE_DDL)
        pruned = agent._prune_schema(
            {"products", "orders"}
        )
        assert "CREATE TABLE products" in pruned
        assert "CREATE TABLE orders" in pruned
        assert "CREATE TABLE customers" not in pruned

    def test_token_count(self, agent):
        """Tokens: count is positive integer."""
        count = agent._count_tokens(SAMPLE_DDL)
        assert count > 0
        assert isinstance(count, int)

    def test_pruned_has_fewer_tokens(self, agent):
        """Tokens: pruned < full schema."""
        agent._build_fk_graph(SAMPLE_DDL)
        full_tokens = agent._count_tokens(SAMPLE_DDL)
        pruned = agent._prune_schema({"products"})
        pruned_tokens = agent._count_tokens(pruned)
        assert pruned_tokens < full_tokens


# --- _singularize helper ---


class TestSingularize:
    """Tests for _singularize helper function."""

    def test_regular_plural(self):
        """Singular: orders -> order."""
        assert _singularize("orders") == "order"

    def test_ies_plural(self):
        """Singular: categories -> category."""
        assert _singularize("categories") == "category"

    def test_already_singular_us(self):
        """Singular: status unchanged."""
        assert _singularize("status") == "status"

    def test_already_singular_ss(self):
        """Singular: address unchanged."""
        assert _singularize("address") == "address"

    def test_already_singular_is(self):
        """Singular: analysis unchanged."""
        assert _singularize("analysis") == "analysis"


# --- _resolve_seeds ---


class TestResolveSeeds:
    """Tests for entity-to-table seed mapping."""

    def test_direct_table_match(self, agent):
        """Seeds: direct table name maps correctly."""
        agent._build_fk_graph(SAMPLE_DDL)
        entities = EntityExtraction(
            tables=["orders"],
            columns=[],
            business_entities=[],
        )
        seeds = agent._resolve_seeds(entities)
        assert "orders" in seeds

    def test_business_entity_revenue(self, agent):
        """Seeds: 'revenue' maps to orders tables."""
        agent._build_fk_graph(SAMPLE_DDL)
        entities = EntityExtraction(
            tables=[],
            columns=[],
            business_entities=["revenue"],
        )
        seeds = agent._resolve_seeds(entities)
        assert "orders" in seeds
        assert "order_items" in seeds

    def test_business_entity_stock(self, agent):
        """Seeds: 'stock' maps to inventory."""
        agent._build_fk_graph(SAMPLE_DDL)
        entities = EntityExtraction(
            tables=[],
            columns=[],
            business_entities=["stock"],
        )
        seeds = agent._resolve_seeds(entities)
        assert "finished_goods_inventory" in seeds

    def test_fallback_when_no_match(self, agent):
        """Seeds: no match falls back to defaults."""
        agent._build_fk_graph(SAMPLE_DDL)
        entities = EntityExtraction(
            tables=["nonexistent"],
            columns=[],
            business_entities=[],
        )
        seeds = agent._resolve_seeds(entities)
        assert "orders" in seeds
        assert "products" in seeds
        assert "customers" in seeds


# --- _fallback_extraction ---


class TestFallbackExtraction:
    """Tests for keyword-based fallback extraction."""

    def test_table_name_match(self, agent):
        """Fallback: exact table name found."""
        agent._build_fk_graph(SAMPLE_DDL)
        result = agent._fallback_extraction(
            "Show all orders",
            list(agent._all_tables),
        )
        assert "orders" in result.tables

    def test_singular_match(self, agent):
        """Fallback: singular form matched."""
        agent._build_fk_graph(SAMPLE_DDL)
        result = agent._fallback_extraction(
            "Show product details",
            list(agent._all_tables),
        )
        assert "products" in result.tables

    def test_no_match_returns_empty(self, agent):
        """Fallback: unrelated query returns empty."""
        agent._build_fk_graph(SAMPLE_DDL)
        result = agent._fallback_extraction(
            "What is the weather?",
            list(agent._all_tables),
        )
        assert result.tables == []


# --- Schema Pruning Cache ---


class TestSchemaPruningCache:
    """
    Tests for schema pruning result caching.
    """

    def test_cache_clear(self, agent):
        """
        Clear empties cache and resets counters.
        """
        agent._cache.set("q1", {"data": "v1"})
        agent._cache.get("q1")  # hit
        agent._cache.clear()
        assert agent._cache.get("q1") is None
        assert agent._cache.hits == 0

    def test_cache_injected_by_default(self):
        """
        Agent has cache by default.
        """
        agent = SchemaIntelligenceAgent()
        assert agent._cache is not None
        assert agent._cache.hits == 0
        assert agent._cache.misses == 0

    def test_cache_stores_pruning_result(self, agent):
        """
        Cache stores and retrieves pruning data.
        """
        agent._build_fk_graph(SAMPLE_DDL)
        selected = agent._find_minimal_tables(
            {"orders"}, max_depth=1
        )
        pruned = agent._prune_schema(selected)
        token_bench = agent._benchmark_tokens(
            SAMPLE_DDL, pruned
        )
        fk_paths = agent._get_fk_paths(selected)

        cache_data = {
            "selected_tables": sorted(selected),
            "pruned_schema": pruned,
            "token_benchmark": token_bench,
            "fk_paths": fk_paths,
            "entities_extracted": {
                "tables": ["orders"],
                "columns": [],
                "business_entities": [],
            },
        }
        agent._cache.set("test query", cache_data)

        cached = agent._cache.get("test query")
        assert cached is not None
        assert "orders" in cached["selected_tables"]
        assert agent._cache.hits == 1

    def test_cached_output_has_execution_step(
        self, agent
    ):
        """
        Cached output includes execution step.
        """
        agent._build_fk_graph(SAMPLE_DDL)
        cache_data = {
            "selected_tables": ["orders"],
            "pruned_schema": "CREATE TABLE orders...",
            "token_benchmark": {
                "full_schema_tokens": 100,
                "pruned_schema_tokens": 30,
                "reduction_pct": 70.0,
            },
            "fk_paths": [],
            "entities_extracted": {
                "tables": ["orders"],
                "columns": [],
                "business_entities": [],
            },
        }
        output = agent._build_cached_output(
            "test query", cache_data, 0.5
        )
        step = output["execution_step"]
        assert step.action == (
            "schema_selection_cache_hit"
        )
        assert step.output_data["cache_hit"] is True
        assert step.duration_ms == 0.5

    def test_different_queries_cached_separately(
        self, agent
    ):
        """
        Different queries are separate entries.
        """
        agent._cache.set("query A", {"data": "A"})
        agent._cache.set("query B", {"data": "B"})
        assert (
            agent._cache.get("query A")["data"] == "A"
        )
        assert (
            agent._cache.get("query B")["data"] == "B"
        )


# --- _get_fk_paths ---


class TestGetFKPaths:
    """Tests for FK path extraction."""

    def test_connected_tables(self, agent):
        """FK paths: connected tables have paths."""
        agent._build_fk_graph(SAMPLE_DDL)
        paths = agent._get_fk_paths(
            {"orders", "customers"}
        )
        assert len(paths) >= 1
        path = paths[0]
        assert "from" in path
        assert "to" in path
        assert "via" in path

    def test_unconnected_tables(self, agent):
        """FK paths: unconnected tables have no paths."""
        agent._build_fk_graph(SAMPLE_DDL)
        paths = agent._get_fk_paths(
            {"products", "customers"}
        )
        assert len(paths) == 0


# --- Context Budget ---


class TestContextBudget:
    """
    Tests for dynamic context budget checking.
    """

    def test_budget_within_limit(self, agent):
        """
        Budget: pruned schema within default budget
        returns positive value.
        """
        agent._build_fk_graph(SAMPLE_DDL)
        pruned = agent._prune_schema({"orders"})
        pruned_tokens = agent._count_tokens(pruned)
        budget = agent._available_token_budget(
            committed_tokens=500
        )
        assert budget > pruned_tokens

    def test_budget_exceeded_returns_negative(
        self, agent
    ):
        """
        Budget: tiny context window yields negative
        available budget.
        """
        import text_to_sql.agents.base as base_mod
        original = base_mod.MODEL_CONTEXT_WINDOWS.get(
            agent.model
        )
        try:
            base_mod.MODEL_CONTEXT_WINDOWS[
                agent.model
            ] = 100
            budget = agent._available_token_budget(
                committed_tokens=50
            )
            # 100 - 50 - 4096 (default reserve) < 0
            assert budget < 0
        finally:
            if original is not None:
                base_mod.MODEL_CONTEXT_WINDOWS[
                    agent.model
                ] = original

    def test_unknown_model_uses_fallback(self):
        """
        Budget: unknown model falls back to
        DEFAULT_CONTEXT_WINDOW.
        """
        from text_to_sql.agents.base import (
            DEFAULT_CONTEXT_WINDOW,
            DEFAULT_OUTPUT_RESERVE,
        )
        agent = SchemaIntelligenceAgent()
        agent.model = "unknown:fake-model"
        budget = agent._available_token_budget(
            committed_tokens=1000
        )
        expected = (
            DEFAULT_CONTEXT_WINDOW
            - 1000
            - DEFAULT_OUTPUT_RESERVE
        )
        assert budget == expected
