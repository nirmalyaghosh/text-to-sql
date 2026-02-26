"""
Unit tests for the standalone SchemaPruner module.

Tests FK graph construction, deterministic entity resolution,
BFS traversal, schema pruning, and token benchmarking.
"""

import json

import pytest

from pathlib import Path

from text_to_sql.schema_pruner import (
    PruneResult,
    SchemaPruner,
    prune_for_query,
)


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
def sample_pruner():
    """
    SchemaPruner with 4-table sample DDL.
    """
    return SchemaPruner(SAMPLE_DDL)


@pytest.fixture
def full_pruner():
    """
    SchemaPruner with full 35-table schema.
    """
    schema_path = (
        Path(__file__).parent.parent / "schema" / "schema_setup.sql"
    )
    ddl = schema_path.read_text(encoding="utf-8")
    return SchemaPruner(ddl)


@pytest.fixture
def golden_queries():
    """
    Load golden queries from evals directory.
    """
    path = (
        Path(__file__).parent.parent / "evals" / "golden_queries.json"
    )
    return json.loads(path.read_text(encoding="utf-8"))


class TestFKGraph:
    """
    Tests for FK graph construction from DDL.
    """

    def test_all_tables_discovered(self, sample_pruner):
        """
        Graph: all tables are discovered.
        """
        assert "products" in sample_pruner._all_tables
        assert "customers" in sample_pruner._all_tables
        assert "orders" in sample_pruner._all_tables
        assert "order_items" in sample_pruner._all_tables
        assert len(sample_pruner._all_tables) == 4

    def test_bidirectional_edges(self, sample_pruner):
        """
        Graph: FK edges are bidirectional.
        """
        assert "customers" in sample_pruner._fk_graph["orders"]
        assert "orders" in sample_pruner._fk_graph["customers"]
        assert "products" in sample_pruner._fk_graph["order_items"]
        assert "order_items" in sample_pruner._fk_graph["products"]

    def test_fk_details_count(self, sample_pruner):
        """
        Graph: correct number of FK edges.
        """
        assert len(sample_pruner._fk_details) == 3
        fk_froms = [d["from"] for d in sample_pruner._fk_details]
        assert "orders" in fk_froms
        assert "order_items" in fk_froms

    def test_table_ddl_extraction(self, sample_pruner):
        """
        Graph: each table's DDL block is extracted.
        """
        assert "products" in sample_pruner._table_ddl
        assert "orders" in sample_pruner._table_ddl
        assert "CREATE TABLE products" in sample_pruner._table_ddl["products"]
        assert "CREATE TABLE orders" in sample_pruner._table_ddl["orders"]

    def test_multi_fk_per_table(self, sample_pruner):
        """
        Graph: all FKs in a table with multiple FKs are captured.
        """
        # order_items has FK to both orders and products
        neighbors = sample_pruner._fk_graph["order_items"]
        assert "orders" in neighbors
        assert "products" in neighbors

    def test_full_schema_table_count(self, full_pruner):
        """
        Graph: full 35-table schema is parsed correctly.
        """
        assert len(full_pruner._all_tables) == 35

    def test_full_schema_fk_edges(self, full_pruner):
        """
        Graph: full schema has substantial FK edges.
        """
        assert len(full_pruner._fk_details) >= 40


class TestResolveTables:
    """
    Tests for deterministic entity resolution.
    """

    def test_direct_table_name(self, full_pruner):
        """
        Layer 1: table name in query resolves to that table.
        """
        seeds = full_pruner.resolve_tables("Show all orders")
        assert "orders" in seeds

    def test_singular_form(self, full_pruner):
        """
        Layer 1: singular form of table name resolves.
        """
        seeds = full_pruner.resolve_tables(
            "Show details for each product"
        )
        assert "products" in seeds

    def test_business_entity_revenue(self, full_pruner):
        """
        Layer 2: 'revenue' maps to orders and order_items.
        """
        seeds = full_pruner.resolve_tables("total revenue")
        assert "orders" in seeds
        assert "order_items" in seeds

    def test_business_entity_shipping(self, full_pruner):
        """
        Layer 2: 'shipping' maps to shipments.
        """
        seeds = full_pruner.resolve_tables(
            "shipping costs by region"
        )
        assert "shipments" in seeds

    def test_column_name_match(self, full_pruner):
        """
        Layer 3: column name in query resolves to parent table.
        """
        seeds = full_pruner.resolve_tables(
            "average unit_cost by supplier"
        )
        assert "raw_materials" in seeds or "suppliers" in seeds

    def test_column_match_skips_resolved_words(self, full_pruner):
        """
        Layer 3: words already resolved by entity map are skipped.
        """
        seeds = full_pruner.resolve_tables(
            "Show total revenue by product category"
        )
        # 'revenue' resolved by entity map (Layer 2) should not
        # also trigger column matching for profitability_analysis
        assert "profitability_analysis" not in seeds

    def test_no_match_returns_fallback(self, full_pruner):
        """
        Fallback: unrelated query returns default tables.
        """
        seeds = full_pruner.resolve_tables(
            "What is the meaning of life?"
        )
        assert "orders" in seeds
        assert "products" in seeds
        assert "customers" in seeds


class TestBFSTraversal:
    """
    Tests for BFS minimal table set selection.
    """

    def test_single_seed_depth_1(self, sample_pruner):
        """
        BFS: single seed at depth=1 finds FK neighbors.
        """
        result = sample_pruner.find_minimal_tables(
            {"orders"}, max_depth=1
        )
        assert "orders" in result
        assert "customers" in result

    def test_depth_limiting_zero(self, sample_pruner):
        """
        BFS: depth=0 returns only seed.
        """
        result = sample_pruner.find_minimal_tables(
            {"orders"}, max_depth=0
        )
        assert result == {"orders"}

    def test_multi_seed(self, sample_pruner):
        """
        BFS: multiple seeds expand correctly.
        """
        result = sample_pruner.find_minimal_tables(
            {"products", "customers"}, max_depth=1
        )
        assert "products" in result
        assert "customers" in result
        assert "order_items" in result
        assert "orders" in result

    def test_empty_seeds(self, sample_pruner):
        """
        BFS: empty seeds return empty set.
        """
        result = sample_pruner.find_minimal_tables(
            set(), max_depth=2
        )
        assert result == set()

    def test_unknown_seed_ignored(self, sample_pruner):
        """
        BFS: unknown table names are silently ignored.
        """
        result = sample_pruner.find_minimal_tables(
            {"nonexistent_table"}, max_depth=2
        )
        assert result == set()


class TestPruneSchema:
    """
    Tests for schema pruning.
    """

    def test_prune_selected_only(self, sample_pruner):
        """
        Pruning: only selected tables included.
        """
        pruned = sample_pruner.prune_schema(
            {"products", "orders"}
        )
        assert "CREATE TABLE products" in pruned
        assert "CREATE TABLE orders" in pruned
        assert "CREATE TABLE customers" not in pruned

    def test_pruned_fewer_tokens(self, sample_pruner):
        """
        Tokens: pruned < full schema.
        """
        full_tokens = sample_pruner.count_tokens(SAMPLE_DDL)
        pruned = sample_pruner.prune_schema({"products"})
        pruned_tokens = sample_pruner.count_tokens(pruned)
        assert pruned_tokens < full_tokens

    def test_token_count_positive(self, sample_pruner):
        """
        Tokens: count is positive integer.
        """
        count = sample_pruner.count_tokens(SAMPLE_DDL)
        assert count > 0
        assert isinstance(count, int)

    def test_empty_selection_returns_empty(self, sample_pruner):
        """
        Pruning: empty selection returns empty string.
        """
        pruned = sample_pruner.prune_schema(set())
        assert pruned == ""


class TestPruneEndToEnd:
    """
    End-to-end tests for the prune() method.
    """

    def test_simple_query(self, full_pruner):
        """
        E2E: simple single-table query.
        """
        result = full_pruner.prune(
            "How many orders were placed?", max_depth=0
        )
        assert "orders" in result.selected_tables
        assert result.reduction_pct > 50

    def test_multi_table_query(self, full_pruner):
        """
        E2E: multi-table query selects correct tables.
        """
        result = full_pruner.prune(
            "Show total revenue by product category",
            max_depth=0,
        )
        assert "orders" in result.selected_tables
        assert "order_items" in result.selected_tables
        assert "products" in result.selected_tables

    def test_result_fields(self, full_pruner):
        """
        E2E: PruneResult has all expected fields.
        """
        result = full_pruner.prune("Show all orders")
        assert isinstance(result, PruneResult)
        assert isinstance(result.query, str)
        assert isinstance(result.seed_tables, list)
        assert isinstance(result.selected_tables, list)
        assert isinstance(result.pruned_schema, str)
        assert isinstance(result.fk_paths, list)
        assert isinstance(result.full_schema_tokens, int)
        assert isinstance(result.pruned_schema_tokens, int)
        assert isinstance(result.reduction_pct, float)

    def test_reduction_positive(self, full_pruner):
        """
        E2E: pruned tokens < full tokens.
        """
        result = full_pruner.prune("Show all orders")
        assert result.pruned_schema_tokens < result.full_schema_tokens
        assert result.reduction_pct > 0

    def test_convenience_function(self):
        """
        E2E: prune_for_query works as a one-shot function.
        """
        schema_path = (
            Path(__file__).parent.parent / "schema" / "schema_setup.sql"
        )
        ddl = schema_path.read_text(encoding="utf-8")
        result = prune_for_query("Show all orders", ddl=ddl)
        assert isinstance(result, PruneResult)
        assert "orders" in result.selected_tables


class TestGoldenQueryRecall:
    """
    Parametrized recall tests against golden queries.
    """

    def test_recall_meets_threshold(
        self, full_pruner, golden_queries
    ):
        """
        Golden queries: recall >= 0.8 for all prunable queries.
        """
        prunable = [
            gq for gq in golden_queries
            if gq["expected_outcome"] == "allowed"
            and gq["expected_tables"]
        ]
        failures = []
        for gq in prunable:
            seeds = full_pruner.resolve_tables(gq["nl_query"])
            selected = full_pruner.find_minimal_tables(
                seeds, max_depth=0
            )
            expected = set(gq["expected_tables"])
            recall = (
                len(expected & selected) / len(expected)
                if expected else 1.0
            )
            if recall < 0.8:
                missing = expected - selected
                failures.append(
                    f"{gq['id']}: recall={recall:.2f}, "
                    f"missing={sorted(missing)}"
                )
        assert not failures, (
            f"Recall < 0.8 for {len(failures)} queries:\n"
            + "\n".join(failures)
        )
