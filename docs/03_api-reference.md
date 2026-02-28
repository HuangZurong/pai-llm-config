# API Reference

## 1. API Design

### 1.1 Core Interface

```python
from pai_llm_config import LLMConfig
# or
from pai_llm_config import config

# Default singleton (recommended) — process-wide cache, thread-safe
cfg = LLMConfig.default()              # Auto-loads llm-config.yaml on first call, returns cached instance thereafter

# Load config — auto-discovery
cfg = LLMConfig.load()                     # Auto-finds llm-config.yaml in project root

# Load config — explicit
cfg = LLMConfig.load(
    config_path="llm-config.yaml",  # Config file path (optional, auto-discovers if omitted)
    profile="production",         # Profile, defaults to LLM_CONFIG_PROFILE env var
    dotenv=True,                  # Whether to load .env file
)

# Reset singleton (for environment switching or testing)
LLMConfig.reset_default()

# Get model config (by name or alias)
model = cfg.get("gpt4o")
model = cfg.get("smart")      # Alias auto-resolved

model.provider                    # "openai-proxy"
model.model                       # "gpt-4o"
model.api_base                    # Provider's api_base: "https://prod-proxy.com/v1"
model.temperature                 # 0.3 (model-level override)
model.max_context                 # 128000
model.capabilities                # ["reasoning", "code", "vision", "function_calling"]
model.cost_per_1k_input           # 0.0025

# Batch get
models = cfg.get_models(["smart", "fast", "cheap"])

# List all available models and aliases
cfg.list_models()              # ["gpt4o", "claude-sonnet", "deepseek-chat", "qwen-local"]
cfg.list_aliases()             # {"smart": "gpt4o", "fast": "deepseek-chat", ...}
```

### 1.2 Routing Interface

Routing methods uniformly return `ModelConfig` objects (same type as `config.get()`), which can be directly passed to `create_client()` and similar methods.

```python
# Static task routing
model = config.route("code_generation")       # -> ModelConfig (gpt4o)
model = config.route("summarization")         # -> ModelConfig (deepseek-chat)
client = config.create_client(model)          # Accepts ModelConfig or str

# Conditional routing
model = config.route_by(
    capabilities=["reasoning", "code"],
    prefer="cheapest",                         # cheapest / fastest / best
)

# Fallback
model = config.get_with_fallback("smart")     # Auto-degrades when gpt4o is unavailable

# Intelligent routing (P2)
model = config.smart_route(
    prompt="Please help me refactor this complex recursive algorithm...",
    strategy="cost_optimized",
)
```

### 1.3 Key Pool Interface

```python
# Check key pool status
pool = config.key_pool("openai-proxy")
pool.status()

# Usage reporting (called internally by framework adapters)
pool.report_usage(key="key1", tokens_in=500, tokens_out=200, cost=0.003)
pool.report_error(key="key3", error=RateLimitError("429"))

# Event callbacks
config.on_key_exhausted(lambda key: notify(f"{key.alias} quota exhausted"))
config.on_key_error(lambda key, err: log(f"{key.alias} error: {err}"))
config.on_budget_warning(lambda model, usage: alert(f"{model} used {usage.percent}%"))
```

### 1.4 Parameter Adapters (Two-Layer Design)

Adapters are split into two layers; choose integration depth as needed:

```
L1 — Config params (dict)    Lightest, zero deps, create clients yourself, pass directly to LangChain/DSPy etc.
L2 — SDK client factory      Returns native SDK clients, with built-in key rotation + usage tracking
```

> **Design philosophy**: No L3 framework adapters. L1 output params can be passed directly to any framework:
> ```python
> ChatOpenAI(**config.params("smart"))          # LangChain (OpenAI SDK format)
> dspy.LM(**config.dspy_params("smart"))        # DSPy (LiteLLM format)
> litellm.completion(**config.litellm_params("smart"), messages=[...])  # LiteLLM
> ```
> L2 provides one-step convenience methods: `config.dspy_client("smart")` returns the pre-configured `dspy` module, `config.litellm_client("smart")` returns a `litellm.Router`.
> Maintaining framework adapters = version coupling + API chasing + import bloat, with very low ROI.

#### L1 — Config Parameter Output (Zero Extra Dependencies)

`to_params()` outputs parameter format based on the provider's `type`:

```python
# OpenAI-compatible provider
params = config.to_params("gpt4o")
# -> {
#     "model": "gpt-4o",
#     "api_key": "sk-xxx",          # Auto-selected from key pool
#     "base_url": "https://proxy.com/v1",
#     "temperature": 0.3,
#     "max_tokens": 2048,
# }
from openai import OpenAI
client = OpenAI(**params)

# Anthropic provider — outputs Anthropic SDK parameter format
params = config.to_params("claude-sonnet")
# -> {
#     "model": "claude-sonnet-4-20250514",
#     "api_key": "sk-ant-xxx",
#     "max_tokens": 2048,            # Required by Anthropic SDK
# }
from anthropic import Anthropic
client = Anthropic(api_key=params.pop("api_key"))

# LiteLLM unified format (abstracts provider differences)
params = config.to_litellm_params("gpt4o")
# -> {"model": "openai/gpt-4o", "api_key": "sk-xxx", "api_base": "https://...", ...}
import litellm
response = litellm.completion(messages=[...], **params)
```

#### L2 — SDK Client Factory (Built-in Key Rotation + Usage Tracking)

`create_client()` returns different SDK clients based on provider type. For type safety, typed factory methods are provided:

```python
# Generic method — returns Union[OpenAI, anthropic.Anthropic], requires manual type checking
client = config.create_client("smart")

# Typed methods (recommended) — full IDE completion, return type is determined
from openai import OpenAI, AsyncOpenAI
client: OpenAI = config.create_openai_client("smart")
async_client: AsyncOpenAI = config.create_async_openai_client("smart")

import anthropic
client: anthropic.Anthropic = config.create_anthropic_client("claude-sonnet")
async_client: anthropic.AsyncAnthropic = config.create_async_anthropic_client("claude-sonnet")

# Raises ProviderTypeMismatchError if provider type doesn't match the method
# e.g.: config.create_openai_client("claude-sonnet") -> ProviderTypeMismatchError

# LiteLLM client (returns litellm.Router, unified interface for any model)
client = config.litellm_client("smart")
response = client.completion(model="smart", messages=[...])

# DSPy client (returns pre-configured dspy module, ready to use)
dspy = config.dspy_client("smart")
qa = dspy.ChainOfThought("question -> answer")
```

#### L2 Client Factory Internal Mechanism

Uses custom httpx Transport layer to intercept requests, avoiding monkey-patching that breaks type safety:

```python
import httpx
from openai import OpenAI

class KeyRotationTransport(httpx.BaseTransport):
    """Intercepts requests at the HTTP layer to inject key rotation and usage reporting.

    Advantages:
    - Does not modify any methods on the SDK object, type safety fully preserved
    - All SDK methods (chat, embeddings, with_options, etc.) automatically controlled
    - Unified handling for streaming and non-streaming requests
    """

    def __init__(self, key_pool: KeyPool, model_config: ModelConfig):
        self._key_pool = key_pool
        self._model_config = model_config
        self._inner = httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        # Select key by strategy before each request, inject Authorization header
        current_key = self._key_pool.get_key()
        request.headers["Authorization"] = f"Bearer {current_key}"

        try:
            response = self._inner.handle_request(request)
            # Extract usage from response and report (non-streaming scenario)
            self._report_usage_if_available(response, current_key)
            return response
        except Exception as e:
            self._key_pool.report_error(key=current_key, error=e)
            raise

    def _report_usage_if_available(self, response: httpx.Response, key: str):
        # Parse usage field from response body and report
        ...


# Internal factory method logic
def create_openai_client(self, name: str) -> OpenAI:
    model_config = self.get(name)
    provider = self._providers[model_config.provider]

    if provider.type != "openai":
        raise ProviderTypeMismatchError(
            f"Model '{name}' uses provider type '{provider.type}', "
            f"use create_anthropic_client() instead"
        )

    transport = KeyRotationTransport(provider.key_pool, model_config)

    return OpenAI(
        api_key="placeholder",           # Actual key injected by transport
        base_url=provider.api_base,
        http_client=httpx.Client(transport=transport),
    )
```

The Anthropic SDK is also httpx-based, using the same Transport interception mechanism.

> **Design decision**: Reasons for choosing httpx Transport over monkey-patching:
>
> 1. Type safety — All SDK object method signatures remain unchanged, IDE completion fully intact
> 2. Full coverage — All API calls (chat, embeddings, files, etc.) automatically go through transport
> 3. Composable — Can stack retry, logging, metrics, and other transport layers
> 4. Streaming-friendly — Unified handling at the HTTP layer, no need to separately patch sync/async/streaming methods

### 1.5 Budget Interface

```python
config.budget.usage_today()                   # Today's global usage
config.budget.usage_today("gpt4o")            # Today's usage for a specific model
config.budget.remaining("gpt4o")              # Today's remaining quota
config.budget.usage_monthly()                 # Monthly usage
```

---
