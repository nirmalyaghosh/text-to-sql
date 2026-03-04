"""
Base Agent class with common functionality for all agents.
"""

import time

from abc import (
    ABC,
    abstractmethod,
)
from typing import (
    Any,
    Dict,
    Optional,
)

from pydantic_ai import Agent as PydanticAgent

from text_to_sql.agents.types import (
    ExecutionChainStep,
    QueryRequest,
)
from text_to_sql.app_logger import get_logger


logger = get_logger(__name__)

DEFAULT_MODEL = "openai:gpt-4o-mini"


class BaseAgent(ABC):
    """
    Base class for all agents in the system.

    Provides common functionality:
    - Logging and tracking
    - Execution timing
    - Result formatting
    - Provenance tracking
    """

    def __init__(
        self,
        agent_name: str,
        system_prompt: str,
        model: str = DEFAULT_MODEL,
    ):
        """
        Initialize a base agent.

        Args:
            agent_name: Unique name for this agent
            (e.g., "Orchestrator", "Security")
            system_prompt: Pydantic AI system prompt
            model: LLM model identifier
        """
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.model = model
        self.pydantic_agent = PydanticAgent(
            model=self.model,
            system_prompt=system_prompt,
        )
        logger.info(f"Initialized {agent_name}")

    async def execute(
        self,
        request: QueryRequest,
        previous_results: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Execute the agent's responsibilities.

        Args:
            request: The query request or context from upstream
            previous_results: Results from earlier agents in the pipeline
            context: Shared conversation state

        Returns:
            Dictionary with agent's output (structure varies by agent)
        """
        start_time = time.time()

        try:
            result = await self._execute_internal(
                request=request,
                previous_results=previous_results,
                context=context)
            duration_ms = (time.time() - start_time) * 1000
            logger.info(f"{self.agent_name} executed successfully "
                        f"in {duration_ms:.2f}ms")
            return result
        except Exception as e:
            duration_ms = (time.time() - start_time) * 1000
            logger.error(
                f"{self.agent_name} failed after {duration_ms:.2f}ms: {str(e)}"
            )
            raise

    @abstractmethod
    async def _execute_internal(
        self,
        request: QueryRequest,
        previous_results: Dict[str, Any],
        context: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Internal execution logic. Implemented by subclasses.

        Returns:
            Agent-specific output dictionary
        """
        pass

    def create_execution_step(
        self,
        action: str,
        input_data: Dict[str, Any],
        output_data: Dict[str, Any],
        veto_reason: Optional[str] = None,
        duration_ms: float = 0.0,
    ) -> ExecutionChainStep:
        """
        Helper to create a provenance tracking entry.

        Args:
            action: Description of what was done
            input_data: Input to this step
            output_data: Output from this step
            veto_reason: If vetoing, the reason why
            duration_ms: Execution time

        Returns:
            ExecutionChainStep for provenance tracking
        """
        return ExecutionChainStep(
            agent_name=self.agent_name,
            action=action,
            input_data=input_data,
            output_data=output_data,
            veto_reason=veto_reason,
            duration_ms=duration_ms,
        )
