"""
Schema Intelligence Agent: FK graph traversal and schema pruning.

Responsibilities:
- Parse DDL to build foreign key graph
- Extract entities from NL query via LLM
- BFS traversal to find minimal table set
- Prune schema to selected tables only
- Benchmark token reduction (before/after)
"""

import re
import time
from collections import defaultdict, deque
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Set,
    Tuple,
)

from pydantic_ai import Agent as PydanticAgent

from text_to_sql.agents.base import BaseAgent
from text_to_sql.agents.cache import (
    CacheBackend,
    InProcessTTLCache,
)
from text_to_sql.agents.types import (
    EntityExtraction,
    QueryRequest,
)
from text_to_sql.app_logger import get_logger
from text_to_sql.db import get_schema_ddl
from text_to_sql.prompts.prompts import get_prompt
from text_to_sql.usage_tracker import (
    log_llm_request,
    log_llm_response,
)


logger = get_logger(__name__)


def _singularize(name: str) -> str:
    """
    Helper function used to strip common plural suffix from a table name.

    Handles -ies (categories -> category) and
    regular -s (orders -> order). Preserves words
    already singular ending in -sis, -us, -ss
    (analysis, status).
    """
    if name.endswith("ies"):
        return name[:-3] + "y"
    if name.endswith("s") and not name.endswith(
        ("ss", "us", "is")
    ):
        return name[:-1]
    return name


class SchemaIntelligenceAgent(BaseAgent):
    """
    Selects minimal table set for a query via FK graph.

    Uses LLM for entity extraction (not keyword matching)
    and deterministic graph traversal for table selection.
    Benchmarks token reduction as a first-class output.
    """

    def __init__(
        self,
        cache: Optional[CacheBackend] = None,
    ):
        """
        Initialize the Schema Intelligence Agent.

        Args:
            cache: Optional cache backend for schema
                pruning results. Defaults to an
                in-process TTL cache (128 entries,
                5 min TTL). Pass None to disable,
                or inject a Redis-backed implementation
                for multi-instance deployments.
        """
        system_prompt = get_prompt("schema_intelligence")
        super().__init__(
            "Schema Intelligence", system_prompt
        )
        self._entity_agent = PydanticAgent(
            model=self.model,
            system_prompt=system_prompt,
            output_type=EntityExtraction,
        )
        self._fk_graph: Dict[str, Set[str]] = {}
        self._fk_details: List[Dict[str, str]] = []
        self._table_ddl: Dict[str, str] = {}
        self._all_tables: Set[str] = set()
        self._schema_loaded = False
        self._cache = (
            cache
            if cache is not None
            else InProcessTTLCache()
        )

    def _build_fk_graph(self, full_ddl: str) -> None:
        """
        Helper function used to parse DDL and build
        the FK adjacency graph.

        Handles both inline FOREIGN KEY and ALTER TABLE
        ADD FOREIGN KEY statements.

        Args:
            full_ddl: Complete schema DDL string
        """
        self._fk_graph = defaultdict(set)
        self._fk_details = []
        self._table_ddl = {}
        self._all_tables = set()

        # Extract table names
        table_pattern = re.compile(
            r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"(\w+)\s*\(",
            re.IGNORECASE,
        )
        for match in table_pattern.finditer(full_ddl):
            self._all_tables.add(match.group(1).lower())

        # Extract CREATE TABLE blocks for pruning
        block_pattern = re.compile(
            r"(CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
            r"(\w+)\s*\(.*?\);)",
            re.DOTALL | re.IGNORECASE,
        )
        for match in block_pattern.finditer(full_ddl):
            tbl = match.group(2).lower()
            self._table_ddl[tbl] = match.group(1)

        # Parse inline FOREIGN KEY per table block
        fk_in_block = re.compile(
            r"FOREIGN\s+KEY\s*\((\w+)\)\s*"
            r"REFERENCES\s+(\w+)\s*\((\w+)\)",
            re.IGNORECASE,
        )
        for tbl, ddl_block in self._table_ddl.items():
            for fk_match in fk_in_block.finditer(
                ddl_block
            ):
                col = fk_match.group(1).lower()
                ref = fk_match.group(2).lower()
                ref_col = fk_match.group(3).lower()
                self._add_fk_edge(
                    tbl, col, ref, ref_col
                )

        # Parse ALTER TABLE ADD FOREIGN KEY
        alter_fk = re.compile(
            r"ALTER\s+TABLE\s+(\w+)\s+"
            r"ADD\s+FOREIGN\s+KEY\s*\((\w+)\)\s*"
            r"REFERENCES\s+(\w+)\s*\((\w+)\)",
            re.IGNORECASE,
        )
        for match in alter_fk.finditer(full_ddl):
            src = match.group(1).lower()
            col = match.group(2).lower()
            ref = match.group(3).lower()
            ref_col = match.group(4).lower()
            self._add_fk_edge(src, col, ref, ref_col)

        self._schema_loaded = True
        logger.info(
            f"FK graph built: {len(self._all_tables)} "
            f"tables, {len(self._fk_details)} FK edges"
        )

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

    async def _execute_internal(
        self,
        request: QueryRequest,
        previous_results: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute schema intelligence pipeline.

        Loads DDL, extracts entities via LLM, selects
        tables via BFS, prunes schema, and benchmarks
        token reduction.
        """
        step_start = time.time()

        try:
            full_ddl = get_schema_ddl(
                llm_context=False
            )
            create_ddl = get_schema_ddl(
                llm_context=True
            )
            if not self._schema_loaded:
                self._build_fk_graph(full_ddl)

            query = (
                previous_results
                .get("refinement", {})
                .get(
                    "refined_query",
                    request.natural_language,
                )
            )

            # Check cache before LLM entity extraction
            cached = self._cache.get(query)
            if cached is not None:
                duration_ms = (
                    (time.time() - step_start) * 1000
                )
                logger.info(
                    f"Schema cache hit: "
                    f"{duration_ms:.2f}ms "
                    f"(hits={self._cache.hits}, "
                    f"misses={self._cache.misses})"
                )
                return self._build_cached_output(
                    query, cached, duration_ms
                )

            entities = (
                await self._extract_entities(
                    query, list(self._all_tables)
                )
            )
            seed_tables = self._resolve_seeds(
                entities
            )
            selected = self._find_minimal_tables(
                seed_tables, max_depth=2
            )
            pruned = self._prune_schema(selected)

            token_bench = self._benchmark_tokens(
                create_ddl, pruned
            )

            # Context budget check: fail explicitly
            # if pruned schema won't fit in the
            # model's context window.
            query_tokens = self._count_tokens(query)
            prompt_tokens = self._count_tokens(
                self.system_prompt
            )
            committed = prompt_tokens + query_tokens
            budget = self._available_token_budget(
                committed
            )
            pruned_tokens = token_bench[
                "pruned_schema_tokens"
            ]
            if pruned_tokens > budget:
                duration_ms = (
                    (time.time() - step_start)
                    * 1000
                )
                logger.warning(
                    f"Pruned schema ({pruned_tokens}"
                    f" tokens) exceeds available "
                    f"budget ({budget} tokens)"
                )
                return {
                    "selected_tables": [],
                    "pruned_schema": "",
                    "token_benchmark": token_bench,
                    "fk_paths": [],
                    "entities_extracted": {},
                    "error": (
                        f"Pruned schema "
                        f"({pruned_tokens} tokens)"
                        f" exceeds context budget "
                        f"({budget} tokens)"
                    ),
                    "execution_step": (
                        self.create_execution_step(
                            action=(
                                "schema_context"
                                "_exceeded"
                            ),
                            input_data={
                                "query": query,
                                "pruned_tokens": (
                                    pruned_tokens
                                ),
                                "budget": budget,
                                "committed": (
                                    committed
                                ),
                            },
                            output_data={
                                "tables": sorted(
                                    selected
                                ),
                                "token_benchmark": (
                                    token_bench
                                ),
                            },
                            veto_reason=(
                                "Pruned schema "
                                "exceeds context "
                                "budget"
                            ),
                            duration_ms=(
                                duration_ms
                            ),
                        )
                    ),
                }

            fk_paths = self._get_fk_paths(selected)

            # Cache the deterministic results
            self._cache.set(query, {
                "selected_tables": sorted(selected),
                "pruned_schema": pruned,
                "token_benchmark": token_bench,
                "fk_paths": fk_paths,
                "entities_extracted": {
                    "tables": entities.tables,
                    "columns": entities.columns,
                    "business_entities": (
                        entities.business_entities
                    ),
                },
            })

            duration_ms = (
                (time.time() - step_start) * 1000
            )
            logger.info(
                f"Schema cache miss: "
                f"{duration_ms:.2f}ms "
                f"(hits={self._cache.hits}, "
                f"misses={self._cache.misses})"
            )

            return self._build_schema_output(
                query, selected, pruned,
                token_bench, fk_paths,
                entities, duration_ms,
            )

        except Exception as e:
            logger.error(
                f"Schema intelligence error: {e}"
            )
            duration_ms = (
                (time.time() - step_start) * 1000
            )
            return {
                "selected_tables": [],
                "pruned_schema": "",
                "token_benchmark": {},
                "fk_paths": [],
                "entities_extracted": {},
                "error": str(e),
                "execution_step": (
                    self.create_execution_step(
                        action=(
                            "schema_selection_error"
                        ),
                        input_data={},
                        output_data={
                            "error": str(e)
                        },
                        veto_reason=(
                            "Schema intelligence "
                            "error"
                        ),
                        duration_ms=duration_ms,
                    )
                ),
            }

    def _benchmark_tokens(
        self,
        full_ddl: str,
        pruned_ddl: str,
    ) -> Dict[str, Any]:
        """
        Count tokens before and after pruning and
        compute the reduction percentage.
        """
        before = self._count_tokens(full_ddl)
        after = self._count_tokens(pruned_ddl)
        reduction = 0.0
        if before > 0:
            reduction = (
                (before - after) / before * 100
            )
        return {
            "full_schema_tokens": before,
            "pruned_schema_tokens": after,
            "reduction_pct": round(reduction, 1),
        }

    def _build_cached_output(
        self,
        query: str,
        cached: Dict[str, Any],
        duration_ms: float,
    ) -> Dict[str, Any]:
        """
        Helper function used to assemble output from
        cached pruning results.

        Builds a fresh ExecutionChainStep (for accurate
        provenance timestamps) but reuses the cached
        tables, schema, and token benchmarks.
        """
        output = dict(cached)
        output["execution_step"] = (
            self.create_execution_step(
                action="schema_selection_cache_hit",
                input_data={"query": query},
                output_data={
                    "tables": cached[
                        "selected_tables"
                    ],
                    "tokens_before": (
                        cached["token_benchmark"]
                        .get("full_schema_tokens", 0)
                    ),
                    "tokens_after": (
                        cached["token_benchmark"]
                        .get("pruned_schema_tokens", 0)
                    ),
                    "reduction_pct": (
                        cached["token_benchmark"]
                        .get("reduction_pct", 0)
                    ),
                    "cache_hit": True,
                },
                duration_ms=duration_ms,
            )
        )
        return output

    def _build_schema_output(
        self,
        query: str,
        selected: Set[str],
        pruned: str,
        token_bench: Dict[str, Any],
        fk_paths: List[Dict[str, str]],
        entities: Any,
        duration_ms: float,
    ) -> Dict[str, Any]:
        """
        Assemble the full output dict with execution
        step metadata.
        """
        entities_data = {
            "tables": entities.tables,
            "columns": entities.columns,
            "business_entities": (
                entities.business_entities
            ),
        }
        output = {
            "selected_tables": sorted(selected),
            "pruned_schema": pruned,
            "token_benchmark": token_bench,
            "fk_paths": fk_paths,
            "entities_extracted": entities_data,
        }
        output["execution_step"] = (
            self.create_execution_step(
                action="schema_selection_complete",
                input_data={"query": query},
                output_data={
                    "tables": sorted(selected),
                    "tokens_before": (
                        token_bench[
                            "full_schema_tokens"
                        ]
                    ),
                    "tokens_after": (
                        token_bench[
                            "pruned_schema_tokens"
                        ]
                    ),
                    "reduction_pct": (
                        token_bench["reduction_pct"]
                    ),
                    "entities_extracted": (
                        entities_data
                    ),
                    "fk_paths": fk_paths,
                },
                duration_ms=duration_ms,
            )
        )

        logger.info(
            f"Schema pruned: "
            f"{len(selected)} tables, "
            f"{token_bench['reduction_pct']:.1f}% "
            f"token reduction"
        )
        return output

    async def _extract_entities(
        self,
        query: str,
        available_tables: List[str],
    ) -> EntityExtraction:
        """
        Helper function used to extract table/entity
        references via LLM.

        Intentionally LLM-powered (not keyword matching)
        to handle synonyms and business terms.

        Args:
            query: Natural language query
            available_tables: List of all table names

        Returns:
            EntityExtraction with identified tables
        """
        tables_str = ", ".join(sorted(available_tables))
        prompt = (
            f"Given these database tables: "
            f"{tables_str}\n\n"
            f"Extract entities from this query:\n"
            f'"{query}"\n\n'
            f"Map business terms to table names. "
            f"For example: 'revenue' relates to "
            f"'orders' and 'order_items', "
            f"'staff' relates to 'employees'."
        )

        try:
            request_id = log_llm_request(
                model=self.model,
                system_prompt=self.system_prompt,
                user_prompt=prompt,
                question=query,
            )
            result = await self._entity_agent.run(
                prompt
            )
            usage = result.usage()
            log_llm_response(
                request_id=request_id,
                model=self.model,
                question=query,
                usage={
                    "input_tokens": (
                        usage.input_tokens
                    ),
                    "output_tokens": (
                        usage.output_tokens
                    ),
                },
                generated_sql=(
                    "[entity_extraction]"
                ),
                trim_sql_preview=False,
            )
            return result.output
        except Exception as e:
            logger.warning(
                f"LLM entity extraction failed: {e}. "
                f"Falling back to keyword matching."
            )
            return self._fallback_extraction(
                query, available_tables
            )

    def _fallback_extraction(
        self,
        query: str,
        available_tables: List[str],
    ) -> EntityExtraction:
        """
        Helper function used to provide keyword-based
        fallback when LLM entity extraction fails.

        Args:
            query: Natural language query
            available_tables: List of all table names

        Returns:
            EntityExtraction from keyword matching
        """
        query_lower = query.lower()
        found_tables = []
        for table in available_tables:
            singular = _singularize(name=table)
            if (
                table in query_lower
                or singular in query_lower
            ):
                found_tables.append(table)
        return EntityExtraction(
            tables=found_tables,
            columns=[],
            business_entities=[],
        )

    def _find_minimal_tables(
        self,
        seed_tables: Set[str],
        max_depth: int = 2,
    ) -> Set[str]:
        """
        Helper function used to find the minimal table
        set via BFS through the FK graph.

        Args:
            seed_tables: Starting tables from entity
                extraction
            max_depth: Maximum FK hops (default: 2)

        Returns:
            Set of table names forming minimal
            connected set
        """
        if not seed_tables:
            return set()

        visited: Set[str] = set()
        queue: deque[Tuple[str, int]] = deque(
            (t, 0) for t in seed_tables
            if t in self._all_tables
        )

        while queue:
            table, depth = queue.popleft()
            if table in visited:
                continue
            visited.add(table)

            if depth < max_depth:
                neighbors = self._fk_graph.get(
                    table, set()
                )
                for neighbor in neighbors:
                    if neighbor not in visited:
                        queue.append(
                            (neighbor, depth + 1)
                        )

        return visited

    def _get_fk_paths(
        self, selected: Set[str]
    ) -> List[Dict[str, str]]:
        """
        Helper function used to get FK relationships
        between selected tables.

        Args:
            selected: Set of selected table names

        Returns:
            List of FK path dictionaries
        """
        paths = []
        for fk in self._fk_details:
            if (
                fk["from"] in selected
                and fk["to"] in selected
            ):
                paths.append({
                    "from": fk["from"],
                    "to": fk["to"],
                    "via": fk["from_col"],
                })
        return paths

    def _prune_schema(
        self, selected: Set[str]
    ) -> str:
        """
        Helper function used to extract CREATE TABLE
        blocks for selected tables only.

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

    def _resolve_seeds(
        self, entities: EntityExtraction
    ) -> Set[str]:
        """
        Helper function used to map extracted entities
        to actual table names.

        Handles direct matches and common synonyms.

        Args:
            entities: LLM-extracted entities

        Returns:
            Set of seed table names for BFS
        """
        seeds: Set[str] = set()

        # Direct table matches
        for table in entities.tables:
            t = table.lower().strip()
            if t in self._all_tables:
                seeds.add(t)

        # Business entity → table mapping
        entity_map = {
            "revenue": {"orders", "order_items"},
            "sales": {"orders", "order_items"},
            "shipping": {"shipments"},
            "delivery": {
                "shipments",
                "delivery_partners",
            },
            "stock": {"finished_goods_inventory"},
            "inventory": {
                "finished_goods_inventory",
            },
            "production": {"production_runs"},
            "manufacturing": {"production_runs"},
            "quality": {"quality_inspections"},
            "marketing": {"campaigns"},
            "profit": {"profitability_analysis"},
            "cost": {"cost_allocations"},
            "forecast": {"demand_forecasts"},
        }
        for entity in entities.business_entities:
            e = entity.lower().strip()
            if e in entity_map:
                seeds.update(entity_map[e])

        if not seeds:
            logger.warning(
                "No seed tables resolved. "
                "Falling back to common tables."
            )
            seeds = {"orders", "products", "customers"}

        return seeds
