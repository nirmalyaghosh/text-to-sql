"""
Query Refinement Agent: Disambiguates and refines natural language queries.

Responsibilities:
- Natural language disambiguation
- Temporal/relative reference resolution ("last year", "next quarter")
- Pronoun resolution ("my", "our", "their")
- Query rewriting for clarity
- Intent validation against supported operations
"""

import calendar
import re
import time
from datetime import (
    datetime,
    timedelta,
)
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from text_to_sql.agents.base import BaseAgent
from text_to_sql.agents.types import QueryRequest
from text_to_sql.app_logger import get_logger
from text_to_sql.prompts.prompts import get_prompt


logger = get_logger(__name__)


class QueryRefinementAgent(BaseAgent):
    """
    High-agency agent that refines natural language queries for clarity.

    Handles disambiguation, temporal resolution, pronoun resolution,
    and validates that queries are within system capabilities.
    """

    def __init__(self):
        """
        Initialize the Query Refinement Agent.
        """
        system_prompt = get_prompt("query_refinement")
        super().__init__(
            "Query Refinement", system_prompt
        )

    async def _detect_ambiguity(
        self, query: str, user_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Helper function used to detect remaining
        ambiguities in the query.

        Examples:
          "best products" → ambiguous: best by sales? profit? quality?
          "top customers" → ambiguous: top by spend? frequency? region?

        Args:
            query: Query to analyze
            user_context: User context for interpretation

        Returns:
            {'has_ambiguity': bool, 'ambiguities': [list]}
        """
        ambiguities = []
        query_lower = query.lower()

        # Detect ambiguous superlatives
        ambiguous_terms = {
            "best": (
                "Could mean: highest revenue, highest "
                "profit, highest quality, or highest "
                "rating"
            ),
            "top": (
                "Could mean: highest count, highest "
                "revenue, highest frequency, or highest "
                "rating"
            ),
            "popular": (
                "Could mean: highest sales volume or "
                "highest customer preference"
            ),
            "average": "Could mean: mean, median, or mode",
            "typical": (
                "Could mean: average, median, or "
                "representative sample"
            ),
        }

        for term, explanation in ambiguous_terms.items():
            if term in query_lower:
                ambiguities.append({"term": term, "explanation": explanation})

        return {
            "has_ambiguity": len(ambiguities) > 0,
            "ambiguities": ambiguities,
        }

    async def _disambiguate_entities(
        self, query: str, context: Dict[str, Any]
    ) -> str:
        """
        Helper function used to map business terms to
        database entities.

        Examples:
          "products" → might mean product names,
                       product IDs, or product details
          "sales" → might mean order_items, transactions,
                    or revenue

        Args:
            query: Query to disambiguate
            context: Conversation context

        Returns:
            Disambiguated query
        """
        # Phase 1: Basic entity mapping
        entity_mappings = {
            "items": "products",
            "goods": "products",
            "orders": "order_items",
            "customers": "customers",
            "staff": "employees",
            "workers": "employees",
            "inventory": "finished_goods_inventory",
            "warehouses": "warehouses",
        }

        refined = query
        for business_term, db_entity in entity_mappings.items():
            if business_term in query.lower():
                if db_entity not in query.lower():
                    refined = re.sub(
                        re.escape(business_term),
                        db_entity,
                        refined,
                        flags=re.IGNORECASE,
                    )
                    logger.debug(
                        f"Mapped entity: '{business_term}' "
                        f"-> '{db_entity}'"
                    )

        return refined

    async def _extract_temporal_info(self, query: str) -> Dict[str, Any]:
        """
        Helper function used to extract temporal info
        from refined query.
        """
        return {
            "has_date_filter": any(
                date_kw in query.lower()
                for date_kw in ["2025", "2024", "january", "february", "march"]
            ),
            "has_relative_time": any(
                rel in query.lower()
                for rel in [
                    "last",
                    "this",
                    "next",
                    "previous",
                    "before",
                    "after",
                    "between",
                ]
            ),
        }

    async def _execute_internal(
        self,
        request: QueryRequest,
        previous_results: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute query refinement.

        Runs the three-step pipeline, validates scope,
        then returns refined query with metadata.
        """
        step_start = time.time()

        try:
            original = request.natural_language
            refined = await self._refine_query(
                original, request, context
            )

            validation = (
                await self._validate_query_scope(refined)
            )
            if not validation.get("valid"):
                return self._validation_failed_result(
                    original, validation,
                    (time.time() - step_start) * 1000,
                )

            return await self._success_result(
                original, refined, request,
                (time.time() - step_start) * 1000,
            )

        except Exception as e:
            logger.error(
                f"Query refinement error: {str(e)}"
            )
            return self._refinement_error_result(
                request.natural_language, str(e),
                (time.time() - step_start) * 1000,
            )

    async def _refine_query(
        self,
        query: str,
        request: QueryRequest,
        context: Dict[str, Any],
    ) -> str:
        """
        Run the three-step refinement pipeline.

        Resolves temporal references, pronouns, and
        entity disambiguation in sequence.
        """
        temporal = (
            await self._resolve_temporal_references(
                query, context
            )
        )
        pronoun = await self._resolve_pronouns(
            temporal,
            request.user_context,
            context,
            conversation_history=(
                request.conversation_history
            ),
        )
        return await self._disambiguate_entities(
            pronoun, context
        )

    async def _success_result(
        self,
        original: str,
        refined: str,
        request: QueryRequest,
        duration_ms: float,
    ) -> Dict[str, Any]:
        """
        Build the success result with ambiguity analysis
        and execution step metadata.
        """
        ambiguity = await self._detect_ambiguity(
            refined, request.user_context
        )
        temporal_info = (
            await self._extract_temporal_info(refined)
        )
        has_ambig = ambiguity.get(
            "has_ambiguity", False
        )

        logger.info(
            f"Query refined in {duration_ms:.2f}ms. "
            f"Original: '{original[:60]}...' -> "
            f"Refined: '{refined[:60]}...'"
        )

        return {
            "valid": True,
            "original_query": original,
            "refined_query": refined,
            "temporal_info": temporal_info,
            "ambiguity_flags": ambiguity.get(
                "ambiguities", []
            ),
            "has_ambiguity": has_ambig,
            "execution_step": self.create_execution_step(
                action="query_refinement_complete",
                input_data={"query": original},
                output_data={
                    "refined_query": refined,
                    "has_ambiguity": has_ambig,
                },
                duration_ms=duration_ms,
            ),
        }

    def _validation_failed_result(
        self,
        query: str,
        validation: Dict[str, Any],
        duration_ms: float,
    ) -> Dict[str, Any]:
        """
        Build result for queries that fail scope
        validation.
        """
        reason = validation.get("reason")
        return {
            "valid": False,
            "reason": reason,
            "execution_step": self.create_execution_step(
                action="query_validation_failed",
                input_data={"query": query},
                output_data={"reason": reason},
                veto_reason=reason,
                duration_ms=duration_ms,
            ),
        }

    def _refinement_error_result(
        self,
        query: str,
        error: str,
        duration_ms: float,
    ) -> Dict[str, Any]:
        """
        Build result for unexpected errors during
        refinement.
        """
        return {
            "valid": False,
            "reason": f"Refinement failed: {error}",
            "execution_step": self.create_execution_step(
                action="query_refinement_error",
                input_data={"query": query},
                output_data={"error": error},
                veto_reason="Refinement error",
                duration_ms=duration_ms,
            ),
        }

    @staticmethod
    def _get_last_month_range(ref_date: datetime) -> str:
        """
        Helper function used to get date range for
        last month.
        """
        first_of_this = ref_date.replace(day=1)
        last_of_prev = first_of_this - timedelta(days=1)
        first_of_prev = last_of_prev.replace(day=1)
        start = first_of_prev.strftime("%Y-%m-%d")
        end = last_of_prev.strftime("%Y-%m-%d")
        return f"between {start} and {end}"

    @staticmethod
    def _get_last_n_days_range(
        ref_date: datetime, n: int
    ) -> str:
        """
        Helper function used to get date range for
        last N days.
        """
        start_date = ref_date - timedelta(days=n)
        start = start_date.strftime("%Y-%m-%d")
        end = ref_date.strftime("%Y-%m-%d")
        return f"between {start} and {end}"

    @staticmethod
    def _get_last_quarter_range(ref_date: datetime) -> str:
        """
        Helper function used to get date range for
        last quarter.
        """
        quarter = (ref_date.month - 1) // 3
        last_quarter = quarter - 1 if quarter > 0 else 3
        last_year = (
            ref_date.year
            if quarter > 0
            else ref_date.year - 1
        )
        start_month = last_quarter * 3 + 1
        end_month = start_month + 2
        _, last_day = calendar.monthrange(
            last_year, end_month
        )
        start_date = ref_date.replace(
            year=last_year, month=start_month, day=1
        )
        end_date = start_date.replace(
            month=end_month, day=last_day
        )
        start = start_date.strftime("%Y-%m-%d")
        end = end_date.strftime("%Y-%m-%d")
        return f"between {start} and {end}"

    @staticmethod
    def _get_last_year_range(ref_date: datetime) -> str:
        """
        Helper function used to get date range for
        last year.
        """
        last_year = ref_date.year - 1
        return f"between {last_year}-01-01 and {last_year}-12-31"

    @staticmethod
    def _get_this_month_range(ref_date: datetime) -> str:
        """
        Helper function used to get date range for
        this month.
        """
        first = ref_date.replace(day=1)
        start = first.strftime("%Y-%m-%d")
        end = ref_date.strftime("%Y-%m-%d")
        return f"between {start} and {end}"

    @staticmethod
    def _get_this_year_range(ref_date: datetime) -> str:
        """
        Helper function used to get date range for
        this year.
        """
        return (
            f"between {ref_date.year}-01-01 and {ref_date.year}-12-31"
        )

    async def _resolve_pronouns(
        self,
        query: str,
        user_context: Dict[str, Any],
        context: Dict[str, Any],
        conversation_history: Optional[
            List[Dict[str, str]]
        ] = None,
    ) -> str:
        """
        Helper function used to resolve pronouns and
        cross-turn references.

        Handles:
        - Personal pronouns: "my", "our", "their"
        - Cross-turn references: "those", "the same",
          "it", "them" (using conversation_history)

        Args:
            query: Query with pronouns
            user_context: User info (name, org, etc.)
            context: Conversation context
            conversation_history: Prior turns for
                cross-turn reference resolution

        Returns:
            Query with pronouns resolved
        """
        refined = query
        user_id = user_context.get(
            "user_id", "unknown_user"
        )
        org_id = user_context.get(
            "org_id", "unknown_org"
        )

        # Personal pronoun resolution
        pronoun_patterns = {
            "my ": f"user_{user_id}'s ",
            "our ": f"organization_{org_id}'s ",
            "their ": "user's ",
        }

        for pronoun, replacement in (
            pronoun_patterns.items()
        ):
            if pronoun in query.lower():
                refined = re.sub(
                    re.escape(pronoun),
                    replacement,
                    refined,
                    flags=re.IGNORECASE,
                )
                logger.debug(
                    f"Resolved pronoun: "
                    f"'{pronoun}' -> "
                    f"'{replacement}'"
                )

        # Cross-turn reference resolution (B4.8)
        if conversation_history:
            refined = self._resolve_cross_turn(
                refined, conversation_history
            )

        return refined

    def _resolve_cross_turn(
        self,
        query: str,
        history: List[Dict[str, str]],
    ) -> str:
        """
        Helper function used to resolve cross-turn
        references using conversation history.

        Handles: "those", "the same", "it", "them",
        "that" when they reference prior query context.

        Args:
            query: Current query
            history: Prior conversation turns

        Returns:
            Query with cross-turn refs resolved
        """
        cross_turn_markers = [
            "those", "the same", "them",
            "that query", "it",
        ]
        query_lower = query.lower()
        has_cross_ref = any(
            marker in query_lower
            for marker in cross_turn_markers
        )

        if not has_cross_ref or not history:
            return query

        # Get the most recent user query from history
        last_query = None
        for turn in reversed(history):
            if turn.get("role") == "user":
                last_query = turn.get("content", "")
                break

        if not last_query:
            return query

        # Append context from prior turn
        refined = (
            f"{query} "
            f"(context from prior query: "
            f"'{last_query}')"
        )
        logger.debug(
            f"Cross-turn resolution: injected "
            f"context from prior query"
        )
        return refined

    async def _resolve_temporal_references(
        self, query: str, context: Dict[str, Any]
    ) -> str:
        """
        Helper function used to convert relative dates
        to absolute dates.

        Examples:
          "last year" → "2025-01-01 to 2025-12-31"
          "last quarter" → "2024-10-01 to 2024-12-31"
          "last 30 days" → "2026-01-22 to 2026-02-21"

        Args:
            query: Original query
            context: Conversation context (may contain reference date)

        Returns:
            Query with temporal references resolved
        """
        refined = query
        reference_date = context.get("reference_date", datetime.now())

        # Simple temporal replacements (Phase 1)
        temporal_patterns = {
            "last year": self._get_last_year_range(reference_date),
            "this year": self._get_this_year_range(reference_date),
            "last month": self._get_last_month_range(reference_date),
            "this month": self._get_this_month_range(reference_date),
            "last quarter": self._get_last_quarter_range(reference_date),
            "last 30 days": self._get_last_n_days_range(reference_date, 30),
            "last 7 days": self._get_last_n_days_range(reference_date, 7),
        }

        for pattern, date_range in temporal_patterns.items():
            if pattern in query.lower():
                refined = re.sub(
                    re.escape(pattern),
                    date_range,
                    refined,
                    flags=re.IGNORECASE,
                )
                logger.debug(
                    f"Resolved temporal: '{pattern}' "
                    f"-> '{date_range}'"
                )

        return refined

    async def _validate_query_scope(self, query: str) -> Dict[str, Any]:
        """
        Helper function used to validate that the query
        is within supported operations.

        Phase 1: Only SELECT queries allowed.

        Args:
            query: Query to validate

        Returns:
            {'valid': bool, 'reason': str}
        """
        query_upper = query.upper().strip()

        # Only SELECT allowed
        if not query_upper.startswith("SELECT"):
            # Check if it's still a natural language query
            dangerous_keywords = [
                "CREATE", "UPDATE", "DELETE", "DROP",
                "INSERT", "ALTER"
            ]
            if any(
                re.search(rf"\b{kw}\b", query_upper)
                for kw in dangerous_keywords
            ):
                return {
                    "valid": False,
                    "reason": (
                        "Only SELECT queries are "
                        "supported. No CREATE, UPDATE, "
                        "DELETE, or DROP allowed."
                    ),
                }

        # Check if it mentions unsupported operations
        unsupported = ["store procedure", "function", "trigger", "view"]
        if any(term in query.lower() for term in unsupported):
            return {
                "valid": False,
                "reason": f"Unsupported operation. Supported: SELECT only.",
            }

        return {"valid": True}
