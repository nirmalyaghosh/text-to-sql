"""
LLM Endpoints Configuration Loader.

Loads llm_endpoints.yaml, validates with
Pydantic, resolves API keys from environment
variables, and provides typed client factories.

Usage:
    from text_to_sql.llm_config import (
        get_client,
        get_model_name,
        load_config,
    )

    config = load_config()
    client = get_client("anthropic-sonnet")

    ep = config.endpoints["deepseek-chat"]
    print(ep.cost.input_per_1m)  # 0.28

    cn = config.by_region("cn-beijing")
    ds = config.by_provider("deepseek")

    roles = config.get_role_endpoints(
        project="chinese-llm-sql-benchmark",
        role="benchmark_targets",
    )

Dependencies:
    pip install pydantic pyyaml python-dotenv
    pip install openai anthropic
"""

from __future__ import annotations

import os
from datetime import date
from pathlib import Path
from typing import (
    Any,
    Literal,
)

import yaml
from dotenv import load_dotenv
from pydantic import (
    BaseModel,
    Field,
)

# ---------------------------------------------------
# Load .env early so api_key resolution works
# ---------------------------------------------------
load_dotenv()

# ---------------------------------------------------
# Project root (for default config path).
# parents[2] resolves:
#   src/text_to_sql/llm_config.py -> project root
# ---------------------------------------------------
_PROJECT_ROOT = (
    Path(__file__).resolve().parents[2]
)

# ---------------------------------------------------
# Models
# ---------------------------------------------------

ProviderName = Literal[
    "anthropic",
    "azure",
    "deepseek",
    "minimax",
    "openai",
    "openrouter",
    "qwen",
]


class CostConfig(BaseModel):
    """
    Token pricing. All rates USD per 1M tokens.

    pricing_url must point to a first-party
    official page only. No aggregators, no
    third-party calculators.
    """

    input_per_1m: float
    output_per_1m: float
    cache_hit_input_per_1m: float | None = None
    pricing_url: str | None = None
    pricing_checked: date | None = None
    pricing_notes: str | None = None

    @property
    def days_since_checked(self) -> int | None:
        """
        Days since pricing was last verified.
        None if never checked.
        """
        if self.pricing_checked is None:
            return None
        return (
            date.today() - self.pricing_checked
        ).days

    def estimate_cost(
        self,
        input_tokens: int,
        output_tokens: int,
        cache_hit: bool = False,
    ) -> float:
        """
        Estimate cost in USD for a single
        request.
        """
        if (
            cache_hit
            and self.cache_hit_input_per_1m
        ):
            input_rate = (
                self.cache_hit_input_per_1m
            )
        else:
            input_rate = self.input_per_1m
        return (
            input_tokens * input_rate
            + output_tokens * self.output_per_1m
        ) / 1_000_000


class DefaultsConfig(BaseModel):
    """
    Default values inherited by all endpoints.
    """

    timeout_seconds: int = 60
    max_retries: int = 3
    retry_backoff_factor: float = 2.0


class EndpointConfig(BaseModel):
    """
    Single LLM endpoint definition.
    """

    name: str = ""
    provider: ProviderName
    model: str
    api_key_env: str
    base_url: str | None = None
    region: str | None = None
    context_window: int | None = None
    cost: CostConfig | None = None
    notes: str | None = None

    # Azure-specific
    azure_deployment: str | None = None
    azure_api_version: str | None = None

    # Inherited defaults (merged at load time)
    timeout_seconds: int = 60
    max_retries: int = 3
    retry_backoff_factor: float = 2.0

    @property
    def api_key(self) -> str:
        """
        Resolve API key from environment.
        Fails loud if missing.
        """
        value = os.environ.get(self.api_key_env)
        if not value:
            raise EnvironmentError(
                f"Missing env var"
                f" '{self.api_key_env}'"
                f" required by endpoint"
                f" '{self.name}'"
            )
        return value

    @property
    def api_key_available(self) -> bool:
        """
        Check if API key is set without
        raising.
        """
        return bool(
            os.environ.get(self.api_key_env)
        )


class LLMConfig(BaseModel):
    """
    Top-level config: all endpoints + role
    mappings.
    """

    defaults: DefaultsConfig = Field(
        default_factory=DefaultsConfig,
    )
    endpoints: dict[str, EndpointConfig] = (
        Field(default_factory=dict)
    )
    roles: dict[str, dict[str, Any]] = Field(
        default_factory=dict,
    )

    def available(
        self,
    ) -> list[EndpointConfig]:
        """
        Return endpoints whose API keys are
        actually set.
        """
        return [
            ep
            for ep in self.endpoints.values()
            if ep.api_key_available
        ]

    def by_provider(
        self,
        provider: ProviderName,
    ) -> list[EndpointConfig]:
        """
        Return all endpoints for a given
        provider.
        """
        return [
            ep
            for ep in self.endpoints.values()
            if ep.provider == provider
        ]

    def by_region(
        self,
        region: str,
    ) -> list[EndpointConfig]:
        """
        Return all endpoints in a given region
        (e.g. 'cn-beijing', 'cn-hangzhou').
        """
        return [
            ep
            for ep in self.endpoints.values()
            if ep.region == region
        ]

    def get_role_endpoints(
        self,
        project: str,
        role: str,
    ) -> list[EndpointConfig]:
        """
        Resolve role assignment to endpoint
        configs. Returns list (role may be a
        list or string).
        """
        mapping = self.roles.get(
            project,
            self.roles.get("default", {}),
        )
        value = mapping.get(role)
        if value is None:
            raise KeyError(
                f"Role '{role}' not found"
                f" in project '{project}'"
                f" or defaults"
            )
        names = (
            value
            if isinstance(value, list)
            else [value]
        )
        return [
            self.endpoints[n] for n in names
        ]


def get_context_window(
    model: str,
    config: LLMConfig | None = None,
    default: int = 8192,
) -> int:
    """
    Look up context window for a model string.

    Matches against endpoint model fields,
    stripping provider prefixes (e.g.
    "openrouter:qwen/qwen3.5-9b" matches
    "qwen/qwen3.5-9b"). Returns default if
    no match found.

    Args:
        model: Model string (pydantic-ai format)
        config: Optional pre-loaded config
        default: Fallback context window
    """
    if config is None:
        config = load_config()
    # Strip provider prefix (e.g. "openrouter:")
    bare = model.split(":", 1)[-1] if ":" in model else model
    for ep in config.endpoints.values():
        if ep.model == bare and ep.context_window:
            return ep.context_window
    return default


def get_client(
    endpoint_name: str,
    config: LLMConfig | None = None,
) -> Any:
    """
    Return a configured provider-native client
    for the named endpoint.

    - anthropic: anthropic.Anthropic
    - openai / azure / deepseek / minimax /
      qwen: openai.OpenAI (OpenAI-compatible)
    """
    if config is None:
        config = load_config()

    ep = config.endpoints[endpoint_name]

    if ep.provider == "anthropic":
        from anthropic import Anthropic
        return Anthropic(
            api_key=ep.api_key,
            timeout=ep.timeout_seconds,
            max_retries=ep.max_retries,
        )

    if ep.provider == "azure":
        from openai import AzureOpenAI
        return AzureOpenAI(
            api_key=ep.api_key,
            azure_endpoint=(
                ep.base_url.rstrip("/")
            ),
            azure_deployment=(
                ep.azure_deployment
                or ep.model
            ),
            api_version=(
                ep.azure_api_version
                or "2024-12-01-preview"
            ),
            timeout=ep.timeout_seconds,
            max_retries=ep.max_retries,
        )

    # openai, deepseek, minimax, openrouter,
    # qwen -> all OpenAI-compatible
    from openai import OpenAI
    kwargs: dict[str, Any] = {
        "api_key": ep.api_key,
        "timeout": ep.timeout_seconds,
        "max_retries": ep.max_retries,
    }
    if ep.base_url:
        kwargs["base_url"] = ep.base_url
    return OpenAI(**kwargs)


def get_model_name(
    endpoint_name: str,
    config: LLMConfig | None = None,
) -> str:
    """
    Return the model string to pass in API
    calls.
    """
    if config is None:
        config = load_config()
    return (
        config.endpoints[endpoint_name].model
    )


def load_config(
    path: str | Path | None = None,
) -> LLMConfig:
    """
    Load and validate config from YAML.

    Defaults to llm_endpoints.yaml in the
    project root.
    """
    if path is None:
        path = (
            _PROJECT_ROOT
            / "llm_endpoints.yaml"
        )
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(
            f"Config not found: {path}"
        )

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    defaults = DefaultsConfig(
        **(raw.get("defaults") or {}),
    )

    endpoints: dict[str, EndpointConfig] = {}
    for name, ep_data in (
        raw.get("endpoints") or {}
    ).items():
        merged = {
            "name": name,
            "timeout_seconds": (
                defaults.timeout_seconds
            ),
            "max_retries": (
                defaults.max_retries
            ),
            "retry_backoff_factor": (
                defaults.retry_backoff_factor
            ),
            **ep_data,
        }
        endpoints[name] = EndpointConfig(
            **merged,
        )

    return LLMConfig(
        defaults=defaults,
        endpoints=endpoints,
        roles=raw.get("roles") or {},
    )


# ---------------------------------------------------
# Quick validation:
#   python -m text_to_sql.llm_config
# ---------------------------------------------------

if __name__ == "__main__":
    STALE_THRESHOLD_DAYS = 30

    cfg = load_config()
    print(
        f"Loaded {len(cfg.endpoints)}"
        f" endpoints:"
    )
    for name, ep in cfg.endpoints.items():
        key_status = (
            "OK"
            if ep.api_key_available
            else "MISSING KEY"
        )
        cost_info = ""
        stale_warning = ""
        if ep.cost:
            cost_info = (
                f"  ("
                f"${ep.cost.input_per_1m:.2f}"
                f" / "
                f"${ep.cost.output_per_1m:.2f}"
                f" per 1M)"
            )
            days = ep.cost.days_since_checked
            if days is None:
                stale_warning = (
                    "  NEVER CHECKED"
                )
            elif days > STALE_THRESHOLD_DAYS:
                stale_warning = (
                    f"  STALE ({days}d ago)"
                )
        print(
            f"  {name:<28}"
            f" {ep.provider:<10}"
            f" {ep.model:<30}"
            f" [{key_status}]"
            f"{cost_info}"
            f"{stale_warning}"
        )

    print(
        f"\nAvailable (key set):"
        f" {len(cfg.available())}"
        f"/{len(cfg.endpoints)}"
    )

    stale = [
        (
            name,
            ep.cost.days_since_checked,
            ep.cost.pricing_url,
        )
        for name, ep in cfg.endpoints.items()
        if (
            ep.cost
            and ep.cost.days_since_checked
            is not None
            and ep.cost.days_since_checked
            > STALE_THRESHOLD_DAYS
        )
    ]
    if stale:
        print(
            f"\n{len(stale)} endpoint(s)"
            f" with pricing older than"
            f" {STALE_THRESHOLD_DAYS} days:"
        )
        for name, days, url in stale:
            print(
                f"  {name}: {days}d -> {url}"
            )

    print("\nRole mappings:")
    for project, roles in cfg.roles.items():
        print(f"  {project}:")
        for role, target in roles.items():
            print(f"    {role}: {target}")
