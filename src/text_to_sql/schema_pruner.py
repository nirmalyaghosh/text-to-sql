"""
Deterministic schema pruner using FK graph traversal.

Parses DDL to build a foreign key adjacency graph, resolves
natural language queries to seed tables via keyword and
column-name matching, and uses BFS to find the minimal
connected table set.

No LLM dependency. Fully reproducible benchmarks.
Only external dependency: tiktoken.
"""

import dataclasses
import re

from collections import defaultdict
from pathlib import Path
from typing import (
    Dict,
    List,
    Set,
    Tuple,
)

import tiktoken

from text_to_sql.app_logger import get_logger


logger = get_logger(__name__)

SCHEMA_DIR = Path(__file__).parent.parent.parent / "schema"

# Business terms that map to specific tables.
# Expanded from the 13-entry map in SchemaIntelligenceAgent.
ENTITY_MAP: Dict[str, Set[str]] = {
    "campaign": {"campaigns"},
    "conversion": {"conversion_funnels"},
    "cost": {"cost_allocations"},
    "customer": {"customers"},
    "delivery": {"shipments", "delivery_partners"},
    "department": {"departments"},
    "employee": {"employees"},
    "forecast": {"demand_forecasts"},
    "inspection": {"quality_inspections"},
    "inventory": {"finished_goods_inventory"},
    "invoice": {"invoices"},
    "manufactured": {"production_runs", "production_lines"},
    "manufacturing": {"production_runs"},
    "marketing": {"campaigns"},
    "material": {"raw_materials"},
    "order": {"orders"},
    "product": {"products"},
    "production": {"production_runs"},
    "profit": {"profitability_analysis"},
    "quality": {"quality_inspections"},
    "return": {"returns"},
    "reorder": {"safety_stock_levels"},
    "revenue": {"orders", "order_items"},
    "safety": {"safety_stock_levels"},
    "sales": {"orders", "order_items"},
    "shipment": {"shipments"},
    "shipping": {"shipments"},
    "staff": {"employees"},
    "stock": {"finished_goods_inventory"},
    "supplier": {"suppliers"},
    "transaction": {"transactions"},
    "variant": {"product_variants"},
    "warehouse": {"warehouses"},
}

# Column names too generic to be useful for table resolution.
COLUMN_STOP_LIST: Set[str] = {
    "created_at",
    "date",
    "description",
    "id",
    "is_active",
    "name",
    "notes",
    "status",
    "type",
    "updated_at",
}


@dataclasses.dataclass
class PruneResult:
    """
    Result of schema pruning for a single query.
    """

    query: str
    seed_tables: List[str]
    selected_tables: List[str]
    pruned_schema: str
    fk_paths: List[Dict[str, str]]
    full_schema_tokens: int
    pruned_schema_tokens: int
    reduction_pct: float


class SchemaPruner:
    """
    Deterministic schema pruner using FK graph traversal.

    Parses DDL to build a foreign key adjacency graph,
    resolves NL queries to seed tables via keyword and
    column-name matching, and uses BFS to find the minimal
    connected table set. No LLM dependency.
    """

    def __init__(self, ddl: str) -> None:
        """
        Initialize the pruner by parsing DDL.

        Args:
            ddl: Full schema DDL string
        """
        self._fk_graph: Dict[str, Set[str]] = defaultdict(set)
        self._fk_details: List[Dict[str, str]] = []
        self._table_ddl: Dict[str, str] = {}
        self._all_tables: Set[str] = set()
        self._column_index: Dict[str, Set[str]] = defaultdict(set)
        self._encoder = tiktoken.get_encoding(
            "o200k_base"  # GPT-4o / 4o-mini tokenizer
        )
        self._full_ddl = ddl
        self._build_fk_graph(ddl)
        self._build_column_index()

    def _add_fk_edge(
        self,
        src_table: str,
        src_col: str,
        ref_table: str,
        ref_col: str,
    ) -> None:
        """
        Helper function used to add a bidirectional
        FK edge to the graph.

        Args:
            src_table: Source table name
            src_col: Source column name
            ref_table: Referenced table name
            ref_col: Referenced column name
        """
        self._fk_graph[src_table].add(ref_table)
        self._fk_graph[ref_table].add(src_table)
        self._fk_details.append({
            "from": src_table,
            "from_col": src_col,
            "to": ref_table,
            "to_col": ref_col,
        })

    def _build_column_index(self) -> None:
        """
        Helper function used to build a mapping from
        column names to their parent tables.

        Parses each table's DDL block to extract column
        names. Excludes generic columns via
        COLUMN_STOP_LIST.
        """
        col_pattern = re.compile(
            r"^\s+(\w+)\s+"
            r"(?:SERIAL|INTEGER|BIGINT|SMALLINT|"
            r"NUMERIC|DECIMAL|VARCHAR|TEXT|BOOLEAN|"
            r"DATE|TIMESTAMP|JSON|JSONB|"
            r"DOUBLE\s+PRECISION|REAL)",
            re.IGNORECASE | re.MULTILINE,
        )
        for table, ddl_block in self._table_ddl.items():
            for match in col_pattern.finditer(ddl_block):
                col_name = match.group(1).lower()
                if col_name not in COLUMN_STOP_LIST:
                    self._column_index[col_name].add(table)

    def _build_fk_graph(self, ddl: str) -> None:
        """
        Helper function used to parse DDL and build
        the FK adjacency graph.

        Handles both inline FOREIGN KEY and ALTER TABLE
        ADD FOREIGN KEY statements.

        Args:
            ddl: Complete schema DDL string
        """
        # Extract table names
        table_pattern = re.compile(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"(\w+)\s*\(",
            re.IGNORECASE,
        )
        for match in table_pattern.finditer(ddl):
            self._all_tables.add(match.group(1).lower())

        # Extract CREATE TABLE blocks for pruning
        block_pattern = re.compile(
            r"(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"(\w+)\s*\(.*?\);)",
            re.DOTALL | re.IGNORECASE,
        )
        for match in block_pattern.finditer(ddl):
            tbl = match.group(2).lower()
            self._table_ddl[tbl] = match.group(1)

        # Parse inline FOREIGN KEY constraints.
        # Process each CREATE TABLE block individually to
        # capture ALL FKs per table (not just the first).
        fk_in_block = re.compile(
            r"FOREIGN\s+KEY\s*\((\w+)\)\s*"
            r"REFERENCES\s+(\w+)\s*\((\w+)\)",
            re.IGNORECASE,
        )
        for table_name, ddl_block in self._table_ddl.items():
            for match in fk_in_block.finditer(ddl_block):
                col = match.group(1).lower()
                ref = match.group(2).lower()
                ref_col = match.group(3).lower()
                self._add_fk_edge(table_name, col, ref, ref_col)

        # Parse ALTER TABLE ADD FOREIGN KEY
        alter_fk = re.compile(
            r"ALTER\s+TABLE\s+(\w+)\s+"
            r"ADD\s+FOREIGN\s+KEY\s*\((\w+)\)\s*"
            r"REFERENCES\s+(\w+)\s*\((\w+)\)",
            re.IGNORECASE,
        )
        for match in alter_fk.finditer(ddl):
            src = match.group(1).lower()
            col = match.group(2).lower()
            ref = match.group(3).lower()
            ref_col = match.group(4).lower()
            self._add_fk_edge(src, col, ref, ref_col)

        logger.info(
            f"FK graph built: {len(self._all_tables)} tables, "
            f"{len(self._fk_details)} FK edges"
        )

    def count_tokens(self, text: str) -> int:
        """
        Count tokens using tiktoken.

        Args:
            text: Text to count tokens for

        Returns:
            Token count
        """
        return len(self._encoder.encode(text))

    def find_minimal_tables(
        self,
        seed_tables: Set[str],
        max_depth: int = 2,
    ) -> Set[str]:
        """
        BFS from seed tables through FK graph.

        Args:
            seed_tables: Starting tables from entity resolution
            max_depth: Maximum FK hops (default: 2)

        Returns:
            Set of table names forming minimal connected set
        """
        if not seed_tables:
            return set()

        visited: Set[str] = set()
        queue: List[Tuple[str, int]] = [
            (t, 0) for t in seed_tables
            if t in self._all_tables
        ]

        while queue:
            table, depth = queue.pop(0)
            if table in visited:
                continue
            visited.add(table)

            if depth < max_depth:
                neighbors = self._fk_graph.get(table, set())
                for neighbor in neighbors:
                    if neighbor not in visited:
                        queue.append((neighbor, depth + 1))

        return visited

    def get_fk_paths(
        self,
        selected: Set[str],
    ) -> List[Dict[str, str]]:
        """
        Get FK relationships between selected tables.

        Args:
            selected: Set of selected table names

        Returns:
            List of FK path dictionaries
        """
        paths = []
        for fk in self._fk_details:
            if fk["from"] in selected and fk["to"] in selected:
                paths.append({
                    "from": fk["from"],
                    "to": fk["to"],
                    "via": fk["from_col"],
                })
        return paths

    def prune(
        self,
        query: str,
        max_depth: int = 2,
    ) -> PruneResult:
        """
        Prune schema for a query: resolve → BFS → prune → benchmark.

        This is the top-level entry point.

        Args:
            query: Natural language query
            max_depth: Maximum FK hops (default: 2)

        Returns:
            PruneResult with pruned schema and metrics
        """
        # Get full schema tokens (CREATE TABLE blocks only)
        create_blocks = _extract_create_blocks(self._full_ddl)
        full_tokens = self.count_tokens(create_blocks)

        # Resolve seed tables from query
        seeds = self.resolve_tables(query)

        # BFS to find minimal table set
        selected = self.find_minimal_tables(seeds, max_depth)

        # Prune schema to selected tables
        pruned = self.prune_schema(selected)

        # Token benchmark
        pruned_tokens = self.count_tokens(pruned)
        reduction = 0.0
        if full_tokens > 0:
            reduction = (full_tokens - pruned_tokens) / full_tokens * 100

        # FK paths between selected tables
        fk_paths = self.get_fk_paths(selected)

        logger.info(
            f"Schema pruned: {len(selected)} tables, "
            f"{reduction:.1f}% token reduction "
            f"({full_tokens} -> {pruned_tokens})"
        )

        return PruneResult(
            query=query,
            seed_tables=sorted(seeds),
            selected_tables=sorted(selected),
            pruned_schema=pruned,
            fk_paths=fk_paths,
            full_schema_tokens=full_tokens,
            pruned_schema_tokens=pruned_tokens,
            reduction_pct=round(reduction, 1),
        )

    def prune_schema(self, selected: Set[str]) -> str:
        """
        Extract CREATE TABLE blocks for selected tables.

        Args:
            selected: Set of table names to include

        Returns:
            Pruned DDL containing only selected tables
        """
        blocks = []
        for table in sorted(selected):
            if table in self._table_ddl:
                blocks.append(self._table_ddl[table])
        return "\n\n".join(blocks)

    def resolve_tables(self, query: str) -> Set[str]:
        """
        Deterministic entity resolution from a NL query.

        Combines three strategies in order:
        1. Direct table name matching (incl. singular forms)
        2. Business entity mapping via ENTITY_MAP
        3. Column name matching via column index
           (skips words already resolved by layers 1-2)

        Args:
            query: Natural language query

        Returns:
            Set of seed table names for BFS
        """
        seeds: Set[str] = set()
        query_lower = query.lower()
        query_words = set(re.findall(r"\w+", query_lower))
        resolved_words: Set[str] = set()

        # Layer 1: Direct table name matching
        for table in self._all_tables:
            singular = table.rstrip("s")
            if table in query_lower:
                seeds.add(table)
                resolved_words.add(table)
            elif singular in query_lower:
                seeds.add(table)
                resolved_words.add(singular)

        # Layer 2: Business entity mapping
        for term, tables in ENTITY_MAP.items():
            if term in query_words:
                seeds.update(tables)
                resolved_words.add(term)

        # Layer 3: Column name matching
        # Skip words already resolved by layers 1-2 to avoid
        # double-counting (e.g. "revenue" as both business
        # entity and column name).
        for col_name, tables in self._column_index.items():
            if len(col_name) < 6:
                continue
            if col_name in resolved_words:
                continue
            if col_name in query_lower:
                seeds.update(tables)

        if not seeds:
            logger.warning(
                "No seed tables resolved. "
                "Falling back to common tables."
            )
            seeds = {"orders", "products", "customers"}

        return seeds


def prune_for_query(
    query: str,
    ddl: str | None = None,
    max_depth: int = 2,
) -> PruneResult:
    """
    One-shot convenience function.

    Loads DDL from schema file if not provided.

    Args:
        query: Natural language query
        ddl: Full schema DDL (loads from file if None)
        max_depth: Maximum FK hops (default: 2)

    Returns:
        PruneResult with pruned schema and metrics
    """
    if ddl is None:
        schema_file = SCHEMA_DIR / "schema_setup.sql"
        ddl = schema_file.read_text(encoding="utf-8")
    pruner = SchemaPruner(ddl)
    return pruner.prune(query, max_depth)


def _extract_create_blocks(ddl: str) -> str:
    """
    Helper function used to extract only CREATE TABLE
    blocks from full DDL.

    Strips comments, DROP statements, and operational
    commands that waste tokens.

    Args:
        ddl: Full schema DDL string

    Returns:
        Concatenated CREATE TABLE blocks
    """
    blocks = re.findall(
        r"(CREATE TABLE\b.*?\);)",
        ddl,
        re.DOTALL,
    )
    return "\n\n".join(blocks)
