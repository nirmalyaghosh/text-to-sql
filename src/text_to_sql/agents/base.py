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

import tiktoken

from pydantic_ai import Agent as PydanticAgent

from text_to_sql.agents.types import (
    ExecutionChainStep,
    QueryRequest,
)
from text_to_sql.app_logger import get_logger


logger = get_logger(__name__)

DEFAULT_MODEL = "openai:gpt-4o-mini"
DEFAULT_OUTPUT_RESERVE = 4096

# Model context windows (input + output tokens).
# Conservative fallback for unknown models.
MODEL_CONTEXT_WINDOWS: Dict[str, int] = {
    "openai:gpt-4o": 128_000,
    "openai:gpt-4o-mini": 128_000,
    "openai:gpt-4-turbo": 128_000,
    "openai:gpt-4": 8_192,
    "openai:gpt-3.5-turbo": 16_385,
}
DEFAULT_CONTEXT_WINDOW = 8_192


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
        self._encoder = tiktoken.encoding_for_model(
            "gpt-4o-mini"
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

    def _available_token_budget(
        self,
        committed_tokens: int,
        output_reserve: int = DEFAULT_OUTPUT_RESERVE,
    ) -> int:
        """
        Helper function used to compute the token
        budget available for additional content (e.g.
        pruned schema) after accounting for tokens
        already committed (system prompt, query) and
        a reserve for model output.

        Args:
            committed_tokens: Tokens already used by
                system prompt, query, etc.
            output_reserve: Tokens reserved for
                model output

        Returns:
            Available token budget (may be negative
            if already over)
        """
        context_window = MODEL_CONTEXT_WINDOWS.get(
            self.model, DEFAULT_CONTEXT_WINDOW
        )
        return (
            context_window
            - committed_tokens
            - output_reserve
        )

    def _count_tokens(self, text: str) -> int:
        """
        Helper function used to count tokens via
        tiktoken.

        Args:
            text: Text to count tokens for

        Returns:
            Token count
        """
        return len(self._encoder.encode(text))

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
