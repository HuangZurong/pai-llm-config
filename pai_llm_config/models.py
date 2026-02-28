from typing import Literal, Dict, Any, List, Optional, Union
from pydantic import (
    BaseModel,
    Field,
    HttpUrl,
    PositiveFloat,
    PositiveInt,
    StringConstraints,
    RootModel,
    ConfigDict,
    AliasChoices,
)
from typing_extensions import Annotated


# Custom Types
ProviderType = Literal["openai", "anthropic", "azure", "litellm"]
KeyStrategyType = Literal["priority", "round_robin", "least_used", "random"]
UsageTrackingBackend = Literal["memory", "sqlite", "redis"]
ModelType = Literal["chat", "embedding"]
ProtocolType = Literal["openai-v1", "anthropic-v1", "google-v1", "azure-v1"]


class KeyConfig(BaseModel):
    """Represents a single API key with its properties."""

    key: Annotated[str, StringConstraints(min_length=1)]
    alias: Optional[str] = None
    priority: Optional[PositiveInt] = None
    daily_limit_usd: Optional[PositiveFloat] = None
    rpm_limit: Optional[PositiveInt] = None  # Requests per minute
    tpm_limit: Optional[PositiveInt] = None  # Tokens per minute


class DefaultsConfig(BaseModel):
    """Global default parameters for models."""

    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = Field(
        None, validation_alias=AliasChoices("temperature", "temp")
    )
    max_tokens: Optional[PositiveInt] = Field(
        None,
        validation_alias=AliasChoices(
            "max_tokens", "max-tokens", "max_completion_tokens"
        ),
    )
    timeout: Optional[PositiveInt] = None
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = None
    stop: Optional[Union[str, List[str]]] = None
    seed: Optional[int] = None
    response_format: Optional[Dict[str, Any]] = None


class ProviderConfig(BaseModel):
    """Configuration for a specific LLM provider."""

    type: ProviderType
    api_key: Optional[Annotated[str, StringConstraints(min_length=1)]] = Field(
        None, validation_alias=AliasChoices("api_key", "api-key", "key", "apikey")
    )
    api_keys: Optional[List[KeyConfig]] = Field(
        None, validation_alias=AliasChoices("api_keys", "api-keys", "keys")
    )
    api_base: Optional[HttpUrl] = Field(
        None,
        validation_alias=AliasChoices(
            "api_base", "api-base", "base_url", "base-url", "baseurl", "endpoint"
        ),
    )
    api_version: Optional[str] = Field(
        None, validation_alias=AliasChoices("api_version", "api-version")
    )
    organization: Optional[str] = None
    project: Optional[str] = None  # For Anthropic
    key_strategy: KeyStrategyType = "priority"  # Provider-level default


class ModelConfig(BaseModel):
    """Configuration for a specific LLM model."""

    provider: Annotated[str, StringConstraints(min_length=1)]
    model: Annotated[str, StringConstraints(min_length=1)]
    type: ModelType = "chat"
    # Cost per 1k tokens, can be omitted if using built-in price list
    cost_per_1k_input: Optional[PositiveFloat] = None
    cost_per_1k_output: Optional[PositiveFloat] = None
    max_context: Optional[PositiveInt] = None
    capabilities: List[str] = Field(default_factory=list)
    latency_tier: Literal["low", "medium", "high"] = "medium"
    dimensions: Optional[PositiveInt] = None  # For embedding models
    # Override provider-level key_strategy
    key_strategy: Optional[KeyStrategyType] = None

    # Physical protocol information (Optional metadata for caller)
    protocol: Optional[ProtocolType] = Field(
        None, validation_alias=AliasChoices("protocol", "api_protocol")
    )

    # Default parameters that can be overridden globally or at model level
    temperature: Optional[Annotated[float, Field(ge=0.0, le=2.0)]] = Field(
        None, validation_alias=AliasChoices("temperature", "temp")
    )
    max_tokens: Optional[PositiveInt] = Field(
        None,
        validation_alias=AliasChoices(
            "max_tokens", "max-tokens", "max_completion_tokens"
        ),
    )
    timeout: Optional[PositiveInt] = None  # In seconds
    top_p: Optional[Annotated[float, Field(ge=0.0, le=1.0)]] = None
    stop: Optional[Union[str, List[str]]] = None
    seed: Optional[int] = None
    response_format: Optional[Dict[str, Any]] = None


class AliasConfig(RootModel[Annotated[str, StringConstraints(min_length=1)]]):
    """Maps a semantic alias to a specific model."""

    pass


class RoutingPreset(RootModel[Annotated[str, StringConstraints(min_length=1)]]):
    """Maps a task type to a model alias/name."""

    pass


class RoutingCondition(BaseModel):
    """Defines a condition for model routing."""

    max_tokens_gt: Optional[PositiveInt] = None
    max_tokens_lt: Optional[PositiveInt] = None
    capabilities: Optional[List[str]] = None
    # Add other conditions as needed


class RoutingRule(BaseModel):
    """A single routing rule with a condition and target model."""

    when: Optional[RoutingCondition] = None
    use: Optional[Annotated[str, StringConstraints(min_length=1)]] = None
    default: Optional[Annotated[str, StringConstraints(min_length=1)]] = (
        None  # Only for the last rule
    )


class RoutingConfig(BaseModel):
    """Configuration for model routing."""

    presets: Dict[str, RoutingPreset] = Field(default_factory=dict)
    rules: List[RoutingRule] = Field(default_factory=list)


class SmartRoutingConfig(BaseModel):
    """Configuration for intelligent routing (P2)."""

    enabled: bool = False
    strategy: Literal[
        "cost_optimized", "quality_first", "latency_first", "balanced"
    ] = "cost_optimized"
    constraints: Optional[Dict[str, Any]] = (
        None  # max_cost_per_request, max_latency_ms, min_quality_score
    )


class FallbackConfig(RootModel[List[Annotated[str, StringConstraints(min_length=1)]]]):
    """Defines fallback chains for models."""

    pass


class BudgetConfig(BaseModel):
    """Defines budget limits."""

    daily_limit_usd: Optional[PositiveFloat] = None
    monthly_limit_usd: Optional[PositiveFloat] = None


class ModelBudgetConfig(BaseModel):
    """Defines budget limits per model."""

    daily_limit_usd: Optional[PositiveFloat] = None


class BudgetsConfig(BaseModel):
    """Overall budget configuration."""

    global_: Optional[BudgetConfig] = Field(None, alias="global")
    per_model: Dict[
        Annotated[str, StringConstraints(min_length=1)], ModelBudgetConfig
    ] = Field(default_factory=dict)


class TrackingConfig(BaseModel):
    """Configuration for usage tracking."""

    backend: UsageTrackingBackend = "sqlite"
    sqlite_path: Optional[str] = None
    redis_url: Optional[str] = None


class ProfileOverride(BaseModel):
    """Defines overrides for specific profiles."""

    defaults: Optional[DefaultsConfig] = None
    providers: Optional[
        Dict[Annotated[str, StringConstraints(min_length=1)], ProviderConfig]
    ] = None
    models: Optional[
        Dict[Annotated[str, StringConstraints(min_length=1)], ModelConfig]
    ] = None
    aliases: Optional[
        Dict[Annotated[str, StringConstraints(min_length=1)], AliasConfig]
    ] = None
    routing: Optional[RoutingConfig] = None
    smart_routing: Optional[SmartRoutingConfig] = None
    fallbacks: Optional[
        Dict[Annotated[str, StringConstraints(min_length=1)], FallbackConfig]
    ] = None
    budgets: Optional[BudgetsConfig] = None
    mappings: Optional[Dict[str, str]] = None
    tracking: Optional[TrackingConfig] = None


class LLMConfigSchema(BaseModel):
    """The root schema for the LLM unified configuration."""

    version: Annotated[str, StringConstraints(min_length=1)] = "1"
    defaults: DefaultsConfig = Field(default_factory=DefaultsConfig)
    providers: Dict[Annotated[str, StringConstraints(min_length=1)], ProviderConfig] = (
        Field(default_factory=dict)
    )
    models: Dict[Annotated[str, StringConstraints(min_length=1)], ModelConfig] = Field(
        default_factory=dict
    )
    aliases: Dict[Annotated[str, StringConstraints(min_length=1)], AliasConfig] = Field(
        default_factory=dict
    )
    routing: RoutingConfig = Field(default_factory=RoutingConfig)
    smart_routing: SmartRoutingConfig = Field(default_factory=SmartRoutingConfig)
    fallbacks: Dict[Annotated[str, StringConstraints(min_length=1)], FallbackConfig] = (
        Field(default_factory=dict)
    )
    budgets: BudgetsConfig = Field(default_factory=BudgetsConfig)
    tracking: TrackingConfig = Field(default_factory=TrackingConfig)
    mappings: Dict[str, str] = Field(default_factory=dict)
    profiles: Dict[Annotated[str, StringConstraints(min_length=1)], ProfileOverride] = (
        Field(default_factory=dict)
    )

    model_config = ConfigDict(
        populate_by_name=True
    )  # Allow alias="global" for global_ field
