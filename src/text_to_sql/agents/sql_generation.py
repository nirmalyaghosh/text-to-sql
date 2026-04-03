"""
SQL Generation Agent: Generates SQL with self-critique loop.

Responsibilities:
- Generate SQL from pruned schema + refined query
- Validate SQL syntax (deterministic)
- Self-critique via second LLM call (B4.3 Reflection)
- Retry on critique failure (max 2 retries)
- Track all attempts in execution chain for provenance
"""

import re
import time
from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from pydantic_ai import Agent as PydanticAgent

from text_to_sql.agents.base import BaseAgent
from text_to_sql.agents.types import (
    GeneratedSQL,
    QueryRequest,
    SQLCritique,
)
from text_to_sql.app_logger import get_logger
from text_to_sql.prompts.prompts import get_prompt
from text_to_sql.usage_tracker import (
    log_llm_request,
    log_llm_response,
)


logger = get_logger(__name__)

MAX_RETRIES = 2
BASE_CONFIDENCE = 0.9
CONFIDENCE_DECAY = 0.15


class SQLGenerationAgent(BaseAgent):
    """
    Generates SQL with a self-critique reasoning loop.

    Implements B4.3 (Reflection & Self-Critique):
    1. Generate SQL from pruned schema + query
    2. Validate syntax (deterministic)
    3. LLM self-critique against schema
    4. Regenerate if issues found (max retries)

    The critique loop uses a separate LLM call with a
    distinct prompt, ensuring genuine review rather than
    self-confirmation bias.
    """

    def __init__(self):
        """
        Initialize the SQL Generation Agent.
        """
        system_prompt = get_prompt("sql_generation")
        super().__init__(
            "SQL Generation", system_prompt
        )
        self._gen_agent = PydanticAgent(
            model=self.model,
            system_prompt=system_prompt,
            output_type=GeneratedSQL,
            model_settings=self._model_settings,
        )
        self._critique_prompt = get_prompt(
            "sql_critique"
        )
        self._critique_agent = PydanticAgent(
            model=self.model,
            system_prompt=self._critique_prompt,
            output_type=SQLCritique,
            model_settings=self._model_settings,
        )
        self._provider_ids: List[str] = []

    async def _critique_sql(
        self,
        sql: str,
        schema: str,
        query: str,
    ) -> SQLCritique:
        """
        Helper function used to self-critique generated
        SQL via a separate LLM call.

        Uses a critique-specific prompt so the critique
        agent sees the SQL as an external artifact to
        review, not its own output.

        Args:
            sql: Generated SQL to review
            schema: Pruned schema for reference
            query: Original NL query

        Returns:
            SQLCritique with validation result
        """
        prompt = (
            f"Review this SQL query for correctness "
            f"against the schema.\n\n"
            f"Schema:\n{schema}\n\n"
            f"Original question: {query}\n\n"
            f"Generated SQL:\n{sql}\n\n"
            f"Check:\n"
            f"1. Are all table names valid?\n"
            f"2. Are all column names correct?\n"
            f"3. Are JOIN conditions correct?\n"
            f"4. Does it answer the question?\n"
            f"5. Any missing WHERE clauses?"
        )
        try:
            request_id = log_llm_request(
                model=self.model,
                system_prompt=(
                    self._critique_prompt
                ),
                user_prompt=prompt,
                question=query,
            )
            result = await self._critique_agent.run(
                prompt
            )
            self._provider_ids.extend(self.extract_provider_ids(result))
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
                    "[critique] "
                    f"valid={result.output.is_valid}"
                ),
                trim_sql_preview=False,
            )
            return result.output
        except Exception as e:
            logger.warning(
                f"Critique LLM failed: {e}. "
                f"Marking as invalid for retry."
            )
            return SQLCritique(
                is_valid=False,
                issues=[
                    f"Critique unavailable: {e}"
                ],
                corrected_sql=None,
            )

    async def _execute_internal(
        self,
        request: QueryRequest,
        previous_results: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute SQL generation with self-critique loop.

        Extracts inputs from prior agents, runs the
        generate-validate-critique loop, and returns the
        final SQL with full provenance.
        """
        step_start = time.time()

        query, pruned_schema, selected_tables = (
            self._get_generation_inputs(
                request, previous_results
            )
        )

        if not pruned_schema:
            logger.error(
                "No pruned schema available. "
                "Cannot generate SQL."
            )
            return self._build_error_result(
                "No schema available for "
                "SQL generation",
                step_start,
            )

        result = await self._run_critique_loop(
            query, pruned_schema, selected_tables
        )
        duration_ms = (
            (time.time() - step_start) * 1000
        )

        return self._build_generation_output(
            query, selected_tables, result,
            duration_ms,
        )

    def _get_generation_inputs(
        self,
        request: QueryRequest,
        previous_results: Dict[str, Any],
    ) -> tuple[str, str, list[str]]:
        """
        Extract query, schema, and tables from previous
        agent results.
        """
        schema_result = previous_results.get(
            "schema", {}
        )
        pruned_schema = schema_result.get(
            "pruned_schema", ""
        )
        selected_tables = schema_result.get(
            "selected_tables", []
        )
        refinement = previous_results.get(
            "refinement", {}
        )
        query = refinement.get(
            "refined_query",
            request.natural_language,
        )
        return query, pruned_schema, selected_tables

    async def _run_critique_loop(
        self,
        query: str,
        schema: str,
        tables: List[str],
    ) -> Dict[str, Any]:
        """
        Run the generate-validate-critique loop.

        Each iteration: generate SQL via LLM, validate
        syntax deterministically, then self-critique via
        a second LLM call. Retries up to MAX_RETRIES
        times on failure.
        """
        history: List[Dict[str, Any]] = []
        final_sql: Optional[str] = None
        explanation = ""
        attempt = 0
        confidence = BASE_CONFIDENCE

        for attempt in range(1, MAX_RETRIES + 2):
            sql, expl, delta, done = (
                await self._process_attempt(
                    attempt, query, schema,
                    tables, history,
                )
            )
            explanation = expl or explanation
            confidence += delta
            if done:
                final_sql = sql
                break

        if final_sql is None and history:
            last = history[-1]
            if last.get("sql"):
                final_sql = last["sql"]
                confidence = max(confidence, 0.3)

        return {
            "final_sql": final_sql,
            "explanation": explanation,
            "confidence": max(confidence, 0.0),
            "attempt": attempt,
            "critique_history": history,
        }

    @staticmethod
    def _record(
        history: List[Dict[str, Any]],
        attempt: int,
        sql: Optional[str],
        critique: str,
        action: str,
    ) -> None:
        """
        Append one entry to the critique history.
        """
        history.append({
            "attempt": attempt,
            "sql": sql,
            "critique": critique,
            "action": action,
        })

    async def _process_attempt(
        self,
        attempt: int,
        query: str,
        schema: str,
        tables: List[str],
        history: List[Dict[str, Any]],
    ) -> tuple[Optional[str], str, float, bool]:
        """
        Process one generate-validate-critique cycle.

        Returns (sql, explanation, confidence_delta, done)
        where done=True means the SQL was accepted.
        """
        gen = await self._generate_sql(
            query=query, schema=schema,
            tables=tables,
            prior_critique=(
                history[-1] if history else None
            ),
        )

        if gen is None:
            self._record(
                history, attempt, None,
                "Generation failed", "failed",
            )
            return None, "", 0, False

        ok, issues = self._validate_syntax(gen.sql)
        if not ok:
            self._record(
                history, attempt, gen.sql,
                f"Syntax issues: {issues}",
                "retry_syntax",
            )
            return (
                None, gen.explanation,
                -CONFIDENCE_DECAY, False,
            )

        critique = await self._critique_sql(
            sql=gen.sql, schema=schema,
            query=query,
        )
        if critique.is_valid:
            self._record(
                history, attempt, gen.sql,
                "No issues found", "accepted",
            )
            return gen.sql, gen.explanation, 0, True

        self._record(
            history, attempt, gen.sql,
            f"Issues: {critique.issues}",
            "retry_critique",
        )

        if critique.corrected_sql:
            ok_corr, corr_issues = (
                self._validate_syntax(
                    critique.corrected_sql
                )
            )
            if ok_corr:
                self._record(
                    history, attempt,
                    critique.corrected_sql,
                    "Using critique correction",
                    "accepted_correction",
                )
                return (
                    critique.corrected_sql,
                    gen.explanation,
                    -CONFIDENCE_DECAY, True,
                )
            self._record(
                history, attempt,
                critique.corrected_sql,
                f"Correction syntax: {corr_issues}",
                "retry_correction",
            )

        return (
            None, gen.explanation,
            -CONFIDENCE_DECAY, False,
        )

    def _build_generation_output(
        self,
        query: str,
        tables: List[str],
        result: Dict[str, Any],
        duration_ms: float,
    ) -> Dict[str, Any]:
        """
        Assemble the final output dict with execution
        step metadata from critique loop results.
        """
        history = result["critique_history"]
        confidence = result["confidence"]
        attempt = result["attempt"]

        output = {
            "final_sql": result["final_sql"],
            "explanation": result["explanation"],
            "confidence_score": confidence,
            "attempt_count": attempt,
            "critique_history": history,
        }
        output["execution_step"] = (
            self.create_execution_step(
                action="sql_generation_complete",
                input_data={
                    "query": query,
                    "tables": tables,
                },
                output_data={
                    "sql": result["final_sql"],
                    "explanation": (
                        result["explanation"]
                    ),
                    "attempts": attempt,
                    "confidence": confidence,
                    "critique_summary": (
                        history[-1]["action"]
                        if history
                        else "none"
                    ),
                    "critique_history": history,
                },
                duration_ms=duration_ms,
                provider_ids=self._provider_ids,
            )
        )
        self._provider_ids = []

        logger.info(
            f"SQL generated in {attempt} "
            f"attempt(s), "
            f"confidence={confidence:.2f}"
        )
        return output

    async def _generate_sql(
        self,
        query: str,
        schema: str,
        tables: List[str],
        prior_critique: Optional[Dict[str, Any]],
    ) -> Optional[GeneratedSQL]:
        """
        Helper function used to generate SQL via LLM
        with structured output.

        Args:
            query: Natural language query
            schema: Pruned schema DDL
            tables: Available table names
            prior_critique: Previous critique for retry

        Returns:
            GeneratedSQL or None if generation fails
        """
        prompt_parts = [
            f"Schema:\n{schema}\n",
            f"Available tables: {', '.join(tables)}\n",
            f"Question: {query}\n",
            "Generate a PostgreSQL SELECT query.",
        ]

        if prior_critique:
            prompt_parts.append(
                f"\nPrevious attempt had issues: "
                f"{prior_critique.get('critique', '')}"
                f"\nPlease fix these issues."
            )

        prompt = "\n".join(prompt_parts)

        # Context budget check
        prompt_tokens = self._count_tokens(prompt)
        system_tokens = self._count_tokens(
            self.system_prompt
        )
        committed = prompt_tokens + system_tokens
        budget = self._available_token_budget(
            committed
        )
        if budget < 0:
            logger.warning(
                f"SQL generation prompt "
                f"({committed} tokens) exceeds "
                f"context budget by "
                f"{abs(budget)} tokens"
            )
            return None

        try:
            request_id = log_llm_request(
                model=self.model,
                system_prompt=self.system_prompt,
                user_prompt=prompt,
                question=query,
            )
            result = await self._gen_agent.run(
                prompt
            )
            self._provider_ids.extend(self.extract_provider_ids(result))
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
                generated_sql=result.output.sql,
            )
            return result.output
        except Exception as e:
            logger.error(
                f"SQL generation LLM failed: {e}"
            )
            return None

    def _build_error_result(
        self,
        error_msg: str,
        step_start: float,
    ) -> Dict[str, Any]:
        """
        Helper function used to build an error result
        when SQL generation cannot proceed.

        Args:
            error_msg: Error description
            step_start: Timestamp for duration calc

        Returns:
            Error result dictionary
        """
        duration_ms = (
            (time.time() - step_start) * 1000
        )
        step = self.create_execution_step(
            action="sql_generation_failed",
            input_data={},
            output_data={"error": error_msg},
            duration_ms=duration_ms,
            provider_ids=self._provider_ids,
        )
        self._provider_ids = []
        return {
            "final_sql": None,
            "explanation": "",
            "confidence_score": 0.0,
            "attempt_count": 0,
            "critique_history": [],
            "execution_step": step,
            "error": error_msg,
        }

    def _validate_syntax(
        self, sql: str
    ) -> tuple[bool, list[str]]:
        """
        Helper function used to validate SQL syntax
        deterministically.

        Checks for common structural issues without
        executing the query.

        Args:
            sql: SQL string to validate

        Returns:
            Tuple of (is_valid, issues_list)
        """
        issues = []
        sql_upper = sql.upper().strip()

        # Must be a SELECT
        if not sql_upper.startswith("SELECT"):
            issues.append(
                "Query must start with SELECT"
            )

        # Check for dangerous operations
        dangerous = [
            "DROP", "DELETE", "INSERT",
            "UPDATE", "ALTER", "TRUNCATE",
        ]
        for keyword in dangerous:
            pattern = rf"\b{keyword}\b"
            if re.search(pattern, sql_upper):
                issues.append(
                    f"Contains disallowed: {keyword}"
                )

        # Basic structure check
        if "FROM" not in sql_upper:
            issues.append("Missing FROM clause")

        # Check balanced parentheses
        if sql.count("(") != sql.count(")"):
            issues.append("Unbalanced parentheses")

        return (len(issues) == 0, issues)
