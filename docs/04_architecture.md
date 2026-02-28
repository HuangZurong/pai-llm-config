# Architecture Design

## 1. Architecture

### 1.1 Package Structure

```
pai-llm-config/
├── pai_llm_config/
│   ├── __init__.py                # Public API: LLMConfig, ModelConfig, config singleton
│   ├── config.py                  # LLMConfig main class
│   ├── models.py                  # Pydantic data models
│   ├── loader.py                  # Multi-source loading + merging + profile overrides
│   ├── resolver.py                # ${VAR} variable resolution
│   │
│   ├── keypool/                   # Multi-key pool management
│   │   ├── __init__.py
│   │   ├── pool.py                # KeyPool manager
│   │   ├── strategies.py          # Key selection strategies
│   │   ├── tracker.py             # Usage tracking (memory / sqlite / redis)
│   │   └── health.py              # Key health checks
│   │
│   ├── clients/                   # L2 — SDK client factory
│   │   ├── __init__.py
│   │   └── factory.py             # ClientFactory main logic (OpenAI / Anthropic / LiteLLM)
│   │
│   ├── routing/                   # Model routing
│   │   ├── __init__.py
│   │   ├── static.py              # Static preset routing
│   │   ├── condition.py           # Conditional rule routing
│   │   └── smart.py               # Intelligent routing (P2)
│   │
│   ├── budget.py                  # Budget control
│   │
│   └── cli.py                     # CLI tools (P2)
│
├── pyproject.toml
├── tests/
└── examples/
```

### 1.2 Core Class Diagram

```
LLMConfig (main entry point)
├── Loader (config loading)
│   ├── YAMLLoader
│   ├── TOMLLoader
│   ├── EnvLoader
│   └── DotenvLoader
│
├── Resolver (variable resolution)
│   └── ${VAR} -> actual value
│
├── ModelRegistry (model registry)
│   ├── ModelConfig (model configuration)
│   └── AliasMap (alias mapping)
│
├── ProviderRegistry (provider registry)
│   └── ProviderConfig
│       └── KeyPool (key pool)
│           ├── KeyConfig
│           ├── Strategy (selection strategy)
│           └── UsageTracker (usage tracking)
│
├── ClientFactory (L2 — SDK client factory)
│   ├── OpenAI / OpenAI-compatible  # Including DeepSeek, Azure, etc.
│   ├── Anthropic native SDK
│   └── LiteLLM unified interface
│   (Built-in: key rotation hooks + automatic usage reporting + default param injection)
│
├── Router (routing engine)
│   ├── StaticRouter (static presets)
│   ├── ConditionRouter (conditional rules)
│   └── SmartRouter (intelligent routing, P2)
│
└── BudgetManager (budget management)
```

### 1.3 Key Pool Core Logic

```python
class KeyPool:
    """Manages multiple API keys for a single provider"""

    def __init__(self, keys: list[KeyConfig], strategy: str):
        self.keys = keys
        self.strategy = load_strategy(strategy)
        self.tracker = UsageTracker()

    def get_key(self) -> str:
        """Returns the optimal key based on current strategy"""
        available = [k for k in self.keys if self._is_available(k)]
        if not available:
            raise AllKeysExhaustedError("All keys exhausted")
        return self.strategy.select(available, self.tracker)

    def _is_available(self, key: KeyConfig) -> bool:
        usage = self.tracker.get_today(key)
        if key.daily_limit_usd and usage.cost >= key.daily_limit_usd:
            return False
        if key.rpm_limit and usage.rpm >= key.rpm_limit:
            return False
        if key.error_count > MAX_CONSECUTIVE_ERRORS:
            return False
        return True

    def report_usage(self, key: str, tokens_in: int, tokens_out: int, cost: float):
        self.tracker.record(key, tokens_in, tokens_out, cost)

    def report_error(self, key: str, error: Exception):
        self.tracker.record_error(key, error)
```

### 1.4 Routing Strategy Interface

```python
from typing import Protocol

class RouterStrategy(Protocol):
    def select(self, prompt: str, candidates: list[ModelConfig]) -> ModelConfig: ...

# Built-in strategies
class CostOptimizedRouter(RouterStrategy):
    """Use the cheapest model capable of handling the task (uses lightweight classifier internally)"""

class QualityFirstRouter(RouterStrategy):
    """Prioritize quality, cost as constraint"""

class LatencyFirstRouter(RouterStrategy):
    """Prioritize speed"""

# External integrations
class RouteLLMRouter(RouterStrategy):
    """Integrate RouteLLM open source solution"""

class UnifyRouter(RouterStrategy):
    """Integrate Unify AI API"""
```

### 1.5 Concurrency Safety

LLM applications typically involve multi-threaded or async concurrent calls; KeyPool and UsageTracker must be thread-safe.

```python
import threading
from asyncio import Lock as AsyncLock

class KeyPool:
    def __init__(self, keys: list[KeyConfig], strategy: str):
        self.keys = keys
        self.strategy = load_strategy(strategy)
        self.tracker = UsageTracker()
        self._lock = threading.Lock()          # Synchronous scenario
        self._async_lock = AsyncLock()          # Async scenario

    def get_key(self) -> str:
        with self._lock:
            available = [k for k in self.keys if self._is_available(k)]
            if not available:
                raise AllKeysExhaustedError("All keys exhausted")
            return self.strategy.select(available, self.tracker)

    async def aget_key(self) -> str:
        async with self._async_lock:
            available = [k for k in self.keys if self._is_available(k)]
            if not available:
                raise AllKeysExhaustedError("All keys exhausted")
            return self.strategy.select(available, self.tracker)
```

UsageTracker concurrency strategy depends on the backend:

- memory — `threading.Lock` protects in-memory data structures
- sqlite — Relies on SQLite's built-in write lock (WAL mode), single connection serialized writes
- redis — Uses Redis atomic operations (INCRBY, HINCRBY), naturally thread-safe

### 1.6 Retry & Key Failover

When an API call fails due to key-related errors (429 Rate Limit, 401 Unauthorized, 403 Forbidden), automatically switches to the next available key and retries:

```python
class KeyRotationTransport(httpx.BaseTransport):
    def handle_request(self, request: httpx.Request) -> httpx.Response:
        last_error = None
        for attempt in range(self._max_retries):
            current_key = self._key_pool.get_key()
            request.headers["Authorization"] = f"Bearer {current_key}"

            try:
                response = self._inner.handle_request(request)
                if response.status_code == 429:
                    self._key_pool.report_error(current_key, RateLimitError())
                    continue                   # Switch key and retry
                self._report_usage_if_available(response, current_key)
                return response
            except Exception as e:
                self._key_pool.report_error(current_key, e)
                last_error = e

        raise AllKeysExhaustedError("All keys unavailable") from last_error
```

Retry strategy configuration:

```yaml
providers:
  openai-proxy:
    type: openai
    retry:
      max_retries: 3 # Max retries (across keys)
      retry_on: [429, 401, 403] # HTTP status codes that trigger retry
      backoff: false # No backoff needed in key rotation scenarios, just switch keys
```

Non-key-related errors (500, network timeout, etc.) do not trigger key rotation and are handled by upper-layer business logic or the SDK's built-in retry mechanism.

### 1.7 Logging Standards

A configuration management library handling API keys and call information must follow security standards for logging:

```python
import logging

logger = logging.getLogger("pai_llm_config")

# Key masking — show only first 6 and last 4 characters
def mask_key(key: str) -> str:
    if len(key) <= 12:
        return "***"
    return f"{key[:6]}...{key[-4:]}"

# Log level conventions:
# DEBUG  — Key selection decisions, parameter merging process (for development debugging)
# INFO   — Client creation, key rotation events, config load completion
# WARNING — Key quota approaching limit, budget alerts, fallback triggered
# ERROR  — All keys exhausted, config load failure
```

Rules:

- All API keys in logs must be masked via `mask_key()`
- Never log full request/response bodies (may contain sensitive user data)
- Use standard `logging` module, no forced logging framework; users can configure their own handlers

### 1.8 Configuration Semantic Validation

Pydantic handles type validation, but the following semantic errors need additional validation during `LLMConfig.load()`:

| Validation Rule | Error Type | Example |
| --- | --- | --- |
| Model's referenced provider must exist | `ProviderNotFoundError` | `provider: nonexistent` |
| Alias target model must exist | `ModelNotFoundError` | `smart: nonexistent-model` |
| All models in fallback chains must exist | `ModelNotFoundError` | `fallbacks.smart: [gpt4o, nonexistent]` |
| Models/aliases in routing rules must exist | `ModelNotFoundError` | `routing.presets.code: nonexistent` |
| Aliases must not conflict with model names | `AliasConflictError` | Alias `gpt4o` conflicts with model name `gpt4o` |
| Chat aliases must not point to embedding models | `ModelTypeMismatchError` | `smart: text-embedding-3` |
| Provider/model refs in profile overrides must exist | `ConfigValidationError` | Profile overrides reference undefined provider |

Validation runs once after config loading completes, before returning the `LLMConfig` instance, collecting all errors and raising them together:

```python
config = LLMConfig.load("llm-config.yaml")
# If semantic errors exist, raises ConfigValidationError with all errors:
# ConfigValidationError: 3 validation errors:
#   - models.gpt4o: provider 'nonexistent' not found
#   - aliases.smart: model 'nonexistent-model' not found
#   - fallbacks.smart[1]: model 'nonexistent' not found
```

---
