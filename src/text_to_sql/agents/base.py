"""
Base Agent class with common functionality for all agents.
"""

import asyncio
import json
import os
import time

from abc import (
    ABC,
    abstractmethod,
)
from typing import (
    Any,
    Dict,
    List,
    Optional,
    Union,
)

import tiktoken

from llm_router_ledger import (
    get_context_window,
    UsageTracker,
)
from openai import AsyncOpenAI
from pydantic_ai import Agent as PydanticAgent
from pydantic_ai.models.openai import OpenAIModel
from pydantic_ai.profiles.openai import OpenAIModelProfile
from pydantic_ai.providers.openai import OpenAIProvider

from text_to_sql.agents.types import (
    ExecutionChainStep,
    QueryRequest,
)
from text_to_sql.app_logger import get_logger


logger = get_logger(__name__)

DEFAULT_MODEL = os.environ.get("PIPELINE_MODEL", "openrouter:qwen/qwen3.5-9b")
OPENROUTER_RUN_TAG = os.environ.get("OPENROUTER_RUN_TAG", "")
OPENROUTER_PROVIDER = os.environ.get("OPENROUTER_PROVIDER", "")
DEFAULT_OUTPUT_RESERVE = 4096
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
        temperature: float = 0.0,
    ):
        """
        Initialize a base agent.

        Args:
            agent_name: Unique name for this agent
            (e.g., "Orchestrator", "Security")
            system_prompt: Pydantic AI system prompt
            model: LLM model identifier
            temperature: Temperature for LLM calls
                (default 0.0 for deterministic output)
        """
        self.agent_name = agent_name
        self.system_prompt = system_prompt
        self.model = model
        extra_body = {}
        run_tag = os.environ.get("OPENROUTER_RUN_TAG", "")
        if run_tag:
            extra_body["user"] = run_tag
        provider = os.environ.get("OPENROUTER_PROVIDER", "")
        if provider and model.startswith("openrouter:"):
            extra_body["provider"] = json.loads(provider)
        if temperature < 0.01 and (
            model.startswith("minimax:")
            or model.startswith("z-ai:")
        ):
            temperature = 0.01
        if model.startswith("z-ai:glm-4.5") or model.startswith("z-ai:glm-4.6"):
            extra_body["thinking"] = {"type": "disabled"}
        settings = {"temperature": temperature}
        if extra_body:
            settings["extra_body"] = extra_body
        if model.startswith("self-hosted:"):
            settings["timeout"] = int(os.environ.get(
                "SELF_HOSTED_TIMEOUT", "180",
            ))
        self._model_settings = settings
        self._resolved_model = self._resolve_model(self.model)
        self.pydantic_agent = PydanticAgent(
            model=self._resolved_model,
            system_prompt=system_prompt,
            model_settings=self._model_settings,
        )
        self._encoder = tiktoken.encoding_for_model(
            "gpt-4o-mini"
        )
        self._zai_client: Optional[AsyncOpenAI] = None
        self._zai_temperature = temperature
        if model.startswith("z-ai:"):
            api_key = os.environ.get("Z_AI_API_KEY", "")
            self._zai_client = AsyncOpenAI(
                base_url="https://api.z.ai/api/paas/v4/",
                api_key=api_key,
                max_retries=5,
                timeout=60,
            )
        self._tracker: UsageTracker | None = None
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
            await asyncio.sleep(float(os.environ.get("LLM_CALL_DELAY", "0")))
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
        context_window = get_context_window(
            model=self.model,
            default=DEFAULT_CONTEXT_WINDOW,
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

    async def _zai_structured_call(
        self,
        system_prompt: str,
        user_prompt: str,
        output_type: type,
    ) -> Any:
        """
        Helper function used to call Z.AI's API
        directly via the OpenAI SDK, bypassing
        pydantic-ai. Embeds the JSON schema in the
        system prompt and parses the response into
        the given Pydantic model.

        Args:
            system_prompt: System prompt for the call
            user_prompt: User prompt for the call
            output_type: Pydantic model class to parse
                the response into

        Returns:
            Parsed Pydantic model instance

        Raises:
            ValueError: If JSON parsing or validation
                fails
        """
        schema_str = json.dumps(output_type.model_json_schema())
        full_system = (
            f"{system_prompt}\n\n"
            f"Always respond with a JSON object "
            f"matching this schema:\n\n"
            f"{schema_str}\n\n"
            f"Return ONLY valid JSON. No markdown "
            f"fencing, no explanation outside the "
            f"JSON object."
        )
        bare_model = self.model[len("z-ai:"):]
        response = await self._zai_client.chat.completions.create(
            model=bare_model,
            messages=[
                {"role": "system", "content": full_system},
                {"role": "user", "content": user_prompt},
            ],
            temperature=self._zai_temperature,
        )
        content = response.choices[0].message.content
        if content.startswith("```"):
            content = content.split("\n", 1)[-1]
            content = content.rsplit("```", 1)[0].strip()
        parsed = json.loads(content)
        usage = response.usage
        return output_type.model_validate(parsed), {
            "input_tokens": (
                usage.prompt_tokens if usage else 0
            ),
            "output_tokens": (
                usage.completion_tokens if usage else 0
            ),
            "provider_id": response.id or "",
        }

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
        provider_ids: Optional[List[str]] = None,
    ) -> ExecutionChainStep:
        """
        Helper to create a provenance tracking entry.

        Args:
            action: Description of what was done
            input_data: Input to this step
            output_data: Output from this step
            veto_reason: If vetoing, the reason why
            duration_ms: Execution time
            provider_ids: OpenRouter generation_ids
                from LLM calls in this step

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
            provider_ids=provider_ids or [],
        )

    @staticmethod
    def extract_provider_ids(result) -> List[str]:
        """
        Helper function used to extract
        provider_response_id values from a Pydantic
        AI RunResult's message history.

        Args:
            result: Pydantic AI RunResult from
                agent.run()

        Returns:
            List of provider_response_id strings
            (empty if none found)
        """
        ids = []
        try:
            for msg in result.all_messages():
                pid = getattr(
                    msg, "provider_response_id", None
                )
                if pid:
                    ids.append(pid)
        except Exception:
            pass
        return ids

    @staticmethod
    def _resolve_model(
        model: str,
    ) -> Union[str, OpenAIModel]:
        """
        Helper function used to resolve a model
        string to a Pydantic AI model. Handles
        'minimax:', 'z-ai:', and 'self-hosted:'
        prefixes by creating OpenAI-compatible
        models pointed at the appropriate endpoint.
        """
        if model.startswith("minimax:"):
            api_key = os.environ.get("MINIMAX_API_KEY", "")
            if not api_key:
                raise EnvironmentError("MINIMAX_API_KEY env var required for minimax: models")
            return OpenAIModel(
                model_name=model[len("minimax:"):],
                provider=OpenAIProvider(
                    base_url="https://api.minimax.io/v1",
                    api_key=api_key,
                ),
            )
        if model.startswith("z-ai:"):
            api_key = os.environ.get("Z_AI_API_KEY", "")
            if not api_key:
                raise EnvironmentError("Z_AI_API_KEY env var required for z-ai: models")
            async_client = AsyncOpenAI(
                base_url="https://api.z.ai/api/paas/v4/",
                api_key=api_key,
                max_retries=5,
                timeout=60,
            )
            return OpenAIModel(
                model_name=model[len("z-ai:"):],
                provider=OpenAIProvider(
                    openai_client=async_client,
                ),
                profile=OpenAIModelProfile(
                    default_structured_output_mode='prompted',
                    supports_json_object_output=False,
                ),
            )
        prefix = "self-hosted:"
        if not model.startswith(prefix):
            return model
        base_url = os.environ.get(
            "SELF_HOSTED_BASE_URL", "",
        )
        if not base_url:
            raise EnvironmentError(
                "SELF_HOSTED_BASE_URL env var"
                " required for self-hosted:"
                " models"
            )
        return OpenAIModel(
            model_name=model[len(prefix):],
            provider=OpenAIProvider(
                base_url=base_url,
                api_key="not-needed",
            ),
        )
