"""
Orchestrator Agent: High-agency orchestrator that forms dynamic teams.

Responsibilities:
- Initial query analysis and intent classification
- Dynamic agent team formation based on context
- Conflict resolution between agents
- Final response assembly with provenance tracking
- Conversation state management
"""

import time

from typing import (
    Any,
    Dict,
    List,
    Optional,
)

from text_to_sql.agents.base import BaseAgent
from text_to_sql.agents.security_governance import (
    SecurityGovernanceAgent,
)
from text_to_sql.agents.types import (
    AgenticResponse,
    ExecutionChainStep,
    QueryRequest,
)
from text_to_sql.app_logger import get_logger
from text_to_sql.prompts.prompts import get_prompt


logger = get_logger(__name__)


class OrchestratorAgent(BaseAgent):
    """
    Main orchestrator that controls agent team formation and flow.

    High Agency Level: Decision-maker, conflict resolver, flow
    controller
    """

    def __init__(self):
        """
        Initialize the Orchestrator Agent.
        """
        system_prompt = get_prompt("orchestrator")
        super().__init__("Orchestrator", system_prompt)
        self.conversation_state = {}
        self.available_agents: Dict[str, Optional[BaseAgent]] = {
            "refinement": None,
            "schema": None,
            "security": None,
            "sql_generation": None,
        }
        # execution_chain is built per-query in
        # process_query() to avoid shared mutable state

    async def _analyze_query(self, request: QueryRequest) -> Dict[str, Any]:
        """
        Helper function used to analyze query complexity
        and intent.

        Returns:
            Dictionary with analysis results
        """
        step_start = time.time()

        # Simple heuristic analysis
        # (will be enhanced with LLM later)
        query_lower = request.natural_language.lower()
        complex_words = [
            "complex", "multiple", "cross", "join",
            "combine", "calculate"
        ]
        is_complex = any(
            word in query_lower for word in complex_words
        )
        requires_schema_mapping = any(
            word in query_lower
            for word in [
                "product",
                "customer",
                "order",
                "inventory",
            ]
        )
        might_be_ambiguous = any(
            word in query_lower
            for word in ["best", "top", "popular", "most", "average"]
        )

        analysis = {
            "complexity": "complex" if is_complex else "simple",
            "requires_schema_mapping": requires_schema_mapping,
            "might_be_ambiguous": might_be_ambiguous,
            "user_role": request.user_context.get("role", "user"),
        }

        duration_ms = (time.time() - step_start) * 1000
        logger.debug(
            f"Query analysis completed in {duration_ms:.2f}ms: {analysis}"
        )

        return analysis

    async def _assemble_response(
        self,
        intermediate_results: Dict[str, Any],
        request: QueryRequest,
        team_sequence: List[str],
        execution_chain: List[ExecutionChainStep],
    ) -> AgenticResponse:
        """
        Helper function used to assemble the final
        response from all agent results.

        Args:
            intermediate_results: Results from agents
            request: Original request
            team_sequence: Order agents executed
            execution_chain: Collected execution steps

        Returns:
            Final AgenticResponse
        """
        logger.debug("Assembling final response")

        # Check if Security blocked the query
        security_result = intermediate_results.get(
            "security", {}
        )
        if security_result.get("veto_reason"):
            return AgenticResponse(
                success=False,
                formatted_answer=(
                    "Query blocked by security policy"
                ),
                error_message=(
                    security_result.get("veto_reason")
                ),
            )

        refinement_result = intermediate_results.get(
            "refinement", {}
        )
        refined_query = refinement_result.get(
            "refined_query",
            request.natural_language,
        )

        # Phase 2: Check for SQL generation result
        sql_result = intermediate_results.get(
            "sql_generation", {}
        )
        generated_sql = sql_result.get("final_sql")

        if generated_sql:
            # Post-generation SQL safety audit
            sec = self.available_agents.get("security")
            if isinstance(sec, SecurityGovernanceAgent):
                role = request.user_context.get("role", "user")
                audit = await sec.audit_generated_sql(
                    sql=generated_sql,
                    user_role=role,
                )
                if not audit.get("safe"):
                    reason = audit.get("reason")
                    logger.warning(
                        "Post-generation audit blocked"
                        f": {reason}"
                    )
                    execution_chain.append(
                        self.create_execution_step(
                            action=(
                                "post_gen_audit_blocked"
                            ),
                            input_data={
                                "sql": generated_sql,
                            },
                            output_data=audit,
                            veto_reason=reason,
                        )
                    )
                    return AgenticResponse(
                        success=False,
                        formatted_answer=(
                            "Generated SQL blocked by "
                            "post-generation safety "
                            "audit"
                        ),
                        error_message=reason,
                        execution_chain=(
                            execution_chain
                        ),
                    )

                # Semantic intent audit
                semantic = (
                    await sec.audit_semantic_intent(
                        nl_query=refined_query,
                        generated_sql=generated_sql,
                    )
                )
                sem_pids = []
                sem_pid = semantic.get("provider_id")
                if sem_pid:
                    sem_pids.append(sem_pid)
                if not semantic.get("safe"):
                    reason = semantic.get("reason")
                    logger.warning(
                        "Semantic audit blocked"
                        f": {reason}"
                    )
                    execution_chain.append(
                        self.create_execution_step(
                            action=(
                                "semantic_audit"
                                "_blocked"
                            ),
                            input_data={
                                "sql": (
                                    generated_sql
                                ),
                                "query": (
                                    refined_query
                                ),
                            },
                            output_data=semantic,
                            veto_reason=reason,
                            provider_ids=sem_pids,
                        )
                    )
                    return AgenticResponse(
                        success=False,
                        formatted_answer=(
                            "Generated SQL blocked"
                            " by semantic intent"
                            " audit"
                        ),
                        error_message=reason,
                        execution_chain=(
                            execution_chain
                        ),
                    )
                elif sem_pids:
                    execution_chain.append(
                        self.create_execution_step(
                            action=(
                                "semantic_audit"
                                "_passed"
                            ),
                            input_data={},
                            output_data={
                                "safe": True,
                            },
                            provider_ids=sem_pids,
                        )
                    )

            # Phase 2 response with SQL
            schema_result = intermediate_results.get(
                "schema", {}
            )
            token_bench = schema_result.get(
                "token_benchmark", {}
            )
            confidence = sql_result.get(
                "confidence_score", 0.75
            )
            attempts = sql_result.get(
                "attempt_count", 1
            )

            summary_parts = [
                f"SQL generated in {attempts} "
                f"attempt(s).",
            ]
            if token_bench:
                summary_parts.append(
                    f"Schema pruned: "
                    f"{token_bench.get('reduction_pct', 0)}"
                    f"% token reduction."
                )

            return AgenticResponse(
                success=True,
                formatted_answer=generated_sql,
                generated_sql=generated_sql,
                natural_language_summary=(
                    " ".join(summary_parts)
                ),
                confidence_score=confidence,
                execution_chain=execution_chain,
            )

        # Fallback: no SQL generation agent available
        return AgenticResponse(
            success=True,
            formatted_answer=(
                f"Query refinement complete: "
                f"'{refined_query}'"
            ),
            confidence_score=0.75,
            execution_chain=execution_chain,
        )

    async def _execute_internal(
        self,
        request: QueryRequest,
        previous_results: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Implement abstract method from BaseAgent.

        For Orchestrator, this is a pass-through to
        process_query.
        """
        if not isinstance(request, QueryRequest):
            raise ValueError(
                "Orchestrator requires QueryRequest"
            )
        response = await self.process_query(request)
        return {
            "success": response.success,
            "formatted_answer": response.formatted_answer,
            "execution_chain": response.execution_chain,
        }

    async def _escalate_to_human(
        self, request: QueryRequest
    ) -> AgenticResponse:
        """
        Helper function used to escalate to human review
        when critical decisions are needed.

        Returns:
            Response indicating escalation
        """
        logger.warning("Escalating to human intervention")
        return AgenticResponse(
            success=False,
            formatted_answer=(
                "This query requires human review due to "
                "security concerns."
            ),
            error_message=(
                "Escalated to human: Security Agent "
                "blocked query"
            ),
        )

    async def _form_team(
        self, analysis: Dict[str, Any]
    ) -> Dict[str, List[str]]:
        """
        Helper function used to dynamically select
        agents based on query analysis.

        Phase 2 pipeline:
        refinement → security → schema → sql_generation

        Returns:
            Dictionary with 'sequence' key
        """
        team = {"sequence": []}

        # Always include refinement and security
        team["sequence"].extend(
            ["refinement", "security"]
        )

        # Phase 2: Add schema + SQL generation
        # if agents are available
        has_schema = (
            self.available_agents.get("schema")
            is not None
        )
        has_sql_gen = (
            self.available_agents.get(
                "sql_generation"
            )
            is not None
        )

        if has_schema:
            team["sequence"].append("schema")
        if has_sql_gen and has_schema:
            team["sequence"].append(
                "sql_generation"
            )

        logger.debug(
            f"Formed team: {team['sequence']}"
        )
        return team

    async def _resolve_conflict(
        self,
        agent_name: str,
        veto_result: Dict[str, Any],
        intermediate_results: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Helper function used to handle veto conflicts
        from agents (typically Security).

        Args:
            agent_name: Agent that raised veto
            veto_result: The veto result with reason
            intermediate_results: Results from prior agents

        Returns:
            Conflict resolution decision
        """
        logger.warning(f"Conflict resolution triggered by {agent_name}")

        # For Phase 1, escalate vetos from Security Agent
        if agent_name == "security":
            return {
                "override": False,
                "escalate": True,
                "reason": veto_result.get("veto_reason"),
            }

        return {
            "override": False,
            "escalate": False,
        }

    def inject_agent(self, agent_name: str, agent_instance: BaseAgent):
        """
        Inject dependency: register an agent instance.

        Args:
            agent_name: Name of agent to register
            agent_instance: Instance of the agent
        """
        self.available_agents[agent_name] = agent_instance
        logger.info(f"Injected agent: {agent_name}")

    async def process_query(
        self, request: QueryRequest
    ) -> AgenticResponse:
        """
        Main entry point: process a user query end-to-end.

        Args:
            request: The user's query with context

        Returns:
            Complete response with provenance tracking
        """
        logger.info(f"Processing query: {request.natural_language[:100]}...")

        start_time = time.time()
        execution_chain: List[ExecutionChainStep] = []

        try:
            # Step 1: Analyze query
            analysis = await self._analyze_query(request)
            logger.debug(f"Query analysis: {analysis}")

            # Step 2: Form dynamic team
            team = await self._form_team(analysis)
            logger.debug(f"Formed team: {team['sequence']}")

            # Step 3: Execute agent pipeline
            intermediate_results = {}
            for agent_name in team["sequence"]:
                agent = self.available_agents.get(agent_name)
                if agent is None:
                    logger.warning(
                        f"Agent {agent_name} not available, "
                        "skipping")
                    continue

                result = await agent.execute(
                    request=request,
                    previous_results=intermediate_results,
                    context=self.conversation_state,
                )

                # Check for veto (Security Agent)
                veto = result.get("veto_reason")
                if veto:
                    logger.warning(
                        f"Agent {agent_name} "
                        f"vetoed: {veto}"
                    )
                    resolution = (
                        await self._resolve_conflict(
                            agent_name,
                            result,
                            intermediate_results,
                        )
                    )
                    if not resolution.get("override"):
                        if resolution.get("escalate"):
                            return (
                                await
                                self._escalate_to_human(
                                    request
                                )
                            )

                # Check security clearance gate
                if (
                    agent_name == "security"
                    and not result.get("allowed", False)
                ):
                    intermediate_results[
                        agent_name
                    ] = result
                    step = result.get(
                        "execution_step"
                    )
                    if step:
                        execution_chain.append(
                            step
                        )
                    break

                intermediate_results[
                    agent_name
                ] = result
                step = result.get("execution_step")
                if step:
                    execution_chain.append(step)

            # Step 4: Assemble final response
            final_response = await self._assemble_response(
                intermediate_results,
                request,
                team["sequence"],
                execution_chain,
            )
            final_response.execution_chain = execution_chain

            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"Query processed in {duration_ms:.2f}ms")
            return final_response

        except Exception as e:
            logger.error(f"Query processing failed: {str(e)}")
            return AgenticResponse(
                success=False,
                formatted_answer="",
                error_message=str(e),
            )

    def set_conversation_state(self, state: Dict[str, Any]):
        """
        Update conversation state (e.g., from prior turns).

        Args:
            state: Conversation state dictionary
        """
        self.conversation_state = state
