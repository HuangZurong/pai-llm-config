# Configuration File Specification

## 1. Configuration File Design

### 1.1 Complete Configuration Example

```yaml
version: "1"

# ============================================================
# Global default parameters
# temperature: 0.0 ~ 2.0, top_p: 0.0 ~ 1.0
# ============================================================
defaults:
  temperature: 0.7
  max_tokens: 2048
  timeout: 30

# ============================================================
# Provider Configuration
# ============================================================
providers:
  # --- Single key (shorthand) ---
  anthropic:
    type: anthropic # Anthropic SDK native protocol
    api_key: ${ANTHROPIC_API_KEY}

  # --- Multi-key pool ---
  openai-proxy:
    type: openai # OpenAI-compatible protocol
    api_base: https://proxy.com/v1
    api_keys:
      - key: ${OPENAI_KEY_1}
        alias: "key1"
        daily_limit_usd: 5
        rpm_limit: 60
        tpm_limit: 100000
        priority: 1

      - key: ${OPENAI_KEY_2}
        alias: "key2"
        daily_limit_usd: 10
        rpm_limit: 120
        priority: 2

      - key: ${OPENAI_KEY_3}
        alias: "key3"
        daily_limit_usd: 3
        priority: 3

    key_strategy: priority # Provider-level default strategy

  # --- Azure ---
  azure:
    type: azure # Azure OpenAI protocol
    api_key: ${AZURE_API_KEY}
    api_base: https://my-resource.openai.azure.com
    api_version: "2024-02-01"

  # --- DeepSeek ---
  deepseek:
    type: openai # DeepSeek is OpenAI-compatible
    api_key: ${DEEPSEEK_API_KEY}
    api_base: https://api.deepseek.com/v1

  # --- Local models ---
  local:
    type: openai # Ollama is OpenAI-compatible
    api_base: http://localhost:11434

  # --- Google Gemini (via OpenAI-compatible endpoint) ---
  google:
    type: openai # Google provides an official OpenAI-compatible endpoint
    api_key: ${GOOGLE_API_KEY}
    api_base: https://generativelanguage.googleapis.com/v1beta/openai/

# ============================================================
# Model Registry
# cost_per_1k_input / cost_per_1k_output can be omitted; the library
# includes built-in default pricing for mainstream models (updated
# periodically). User-configured values take precedence.
# ============================================================
models:
  gpt4o:
    provider: openai-proxy
    model: gpt-4o
    # cost_per_1k_input / cost_per_1k_output omitted, using built-in defaults
    max_context: 128000
    capabilities: [reasoning, code, vision, function_calling]
    latency_tier: medium # low / medium / high
    temperature: 0.3 # Overrides global default
    key_strategy: priority # Model-level override of provider's key_strategy (expensive models prefer high-priority keys)

  claude-sonnet:
    provider: anthropic
    model: claude-sonnet-4-20250514
    max_context: 200000
    capabilities: [reasoning, code, function_calling]
    latency_tier: medium

  deepseek-chat:
    provider: deepseek
    model: deepseek-chat
    cost_per_1k_input: 0.0001 # Non-mainstream models need manual pricing
    cost_per_1k_output: 0.0002
    max_context: 64000
    capabilities: [reasoning, code, function_calling]
    latency_tier: low

  qwen-local:
    provider: local
    model: ollama_chat/qwen2.5
    cost_per_1k_input: 0
    cost_per_1k_output: 0
    max_context: 32000
    capabilities: [reasoning, code]
    latency_tier: low

  gemini-2-flash:
    provider: google
    model: gemini-2.0-flash
    max_context: 1048576
    capabilities: [reasoning, code, vision, function_calling]
    latency_tier: low

  # --- Embedding model ---
  text-embedding-3:
    provider: openai-proxy
    model: text-embedding-3-small
    type: embedding # Marks this as an embedding model
    cost_per_1k_input: 0.00002
    dimensions: 1536
    max_context: 8191

# ============================================================
# Semantic Aliases
# ============================================================
aliases:
  smart: gpt4o
  fast: deepseek-chat
  cheap: qwen-local
  balanced: claude-sonnet

# ============================================================
# Task Routing
# ============================================================
routing:
  # Static presets
  presets:
    code_generation: smart
    summarization: fast
    classification: cheap
    complex_reasoning: smart
    translation: balanced
    chat: fast

  # Conditional rules (matched in order, stops on first match)
  rules:
    - when:
        max_tokens_gt: 4000
        capabilities: [reasoning]
      use: smart

    - when:
        max_tokens_lt: 500
      use: cheap

    - default: balanced

# ============================================================
# Intelligent Routing (P2)
# ============================================================
smart_routing:
  enabled: false
  strategy: cost_optimized # cost_optimized / quality_first / latency_first / balanced
  constraints:
    max_cost_per_request: 0.05
    max_latency_ms: 3000
    min_quality_score: 0.8

# ============================================================
# Fallback Chains
# ============================================================
fallbacks:
  smart: [gpt4o, claude-sonnet, deepseek-chat]
  fast: [deepseek-chat, qwen-local]

# ============================================================
# Budget Control
# ============================================================
budgets:
  global:
    daily_limit_usd: 50
    monthly_limit_usd: 1000
  per_model:
    gpt4o:
      daily_limit_usd: 30
    claude-sonnet:
      daily_limit_usd: 20

# ============================================================
# Usage Tracking
# ============================================================
tracking:
  backend: sqlite # memory / sqlite / redis
  sqlite_path: ~/.pai-llm-config/usage.db
  # redis_url: redis://localhost:6379/0

# ============================================================
# External Name Mappings (adapts third-party hardcoded model names)
# ============================================================
mappings:
  "openai/gpt-4": smart
  "gpt-4": smart
  "gpt-4o": gpt4o

# ============================================================
# Multi-environment Overrides (Profiles)
# ============================================================
profiles:
  development:
    providers:
      openai-proxy:
        api_base: https://dev-proxy.com/v1
    defaults:
      temperature: 0.9 # More randomness in dev

  production:
    providers:
      openai-proxy:
        api_base: https://prod-proxy.com/v1
    defaults:
      temperature: 0.3 # More stability in production
```

### 1.2 Configuration Priority (Highest to Lowest)

```
Environment variables > .env file > Profile overrides (profiles.{name}) > Config file body > defaults
```

### 1.3 Single Key & Multi-Key Compatibility

```yaml
# Single key shorthand — backward compatible, zero migration cost
providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}

# Multi-key full syntax
providers:
  openai-proxy:
    api_keys:
      - key: ${KEY_1}
        priority: 1
      - key: ${KEY_2}
        priority: 2
    key_strategy: priority
```

Internally, both are unified into a KeyPool; a single key is equivalent to a key pool with one element.

`key_strategy` supports two-level configuration: provider-level sets the default strategy, model-level can override. Different models under the same provider can use different strategies (e.g., GPT-4 uses `priority` to save money, GPT-3.5 uses `round_robin` to distribute load). If model-level is not configured, it inherits the provider-level strategy.

### 1.4 Provider Types

Each provider must declare a `type` field, which determines which SDK protocol to use:

| type | Description | Corresponding SDK |
| --- | --- | --- |
| `openai` | OpenAI-compatible protocol (including proxies, DeepSeek, Ollama, etc.) | `openai` |
| `anthropic` | Anthropic native protocol | `anthropic` |
| `azure` | Azure OpenAI protocol | `openai` (Azure mode) |
| `litellm` | Unified proxy via LiteLLM | `litellm` |

The `type` field cannot be omitted. If missing, `ConfigValidationError` is raised at load time.

> **Design decision**: No auto-inference. Provider names are user-defined (e.g., `openai-proxy`, `my-company-gateway`) and cannot reliably infer protocol type. Explicit declaration removes ambiguity and makes the config file self-documenting.

### 1.5 Minimal Configuration

For the simple "one provider + one model" scenario, the minimal usable configuration is:

```yaml
version: "1"

providers:
  openai:
    type: openai
    api_key: ${OPENAI_API_KEY}

models:
  gpt4o:
    provider: openai
    model: gpt-4o
```

Usage:

```python
from pai_llm_config import LLMConfig

config = LLMConfig()
client = config.create_client("gpt4o")
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Hello"}]
)
```

Undeclared parameters (temperature, max_tokens, etc.) use SDK defaults; there is no requirement to configure defaults, aliases, routing, or other advanced features.

### 1.6 Profile Override Scope

The `profiles` block supports overriding the following top-level fields:

| Field | Overridable | Description |
| --- | --- | --- |
| `defaults` | Yes | Override global default parameters |
| `providers` | Yes | Override provider api_base, api_key, etc. |
| `models` | Yes | Override model parameters (e.g., temperature) |
| `aliases` | Yes | Point to different models in different environments |
| `routing` | Yes | Use different routing rules in different environments |
| `budgets` | Yes | Set different budgets in different environments |
| `tracking` | Yes | Use different tracking backends in different environments |
| `fallbacks` | Yes | Use different fallback chains in different environments |
| `mappings` | Yes | Use different external name mappings in different environments |

Overrides use a deep merge strategy: profile config is recursively merged with the main config, with profile config taking priority. List-type fields (e.g., `api_keys`) are replaced entirely rather than appended.

### 1.7 Config File Auto-Discovery

When `LLMConfig.load()` is called without a path, it automatically finds the config file from the project root — zero configuration needed.

#### Discovery Strategy

1. Determine project root (by priority):

   - Environment variable `LLM_CONFIG_ROOT` (explicit override)
   - `flashboot_core.utils.project_utils.get_project_root()` (if installed)
   - Walk up to find marker files like `pyproject.toml` / `.git` (built-in fallback)

2. Search for config files from the project root (stops on first match):

```
{root}/llm-config.yaml
{root}/llm-config.yml
{root}/config/llm-config.yaml
{root}/config/llm-config.yml
{root}/resources/llm-config.yaml
{root}/resources/llm-config.yml
{root}/.llm-config.yaml              # Hidden file style
```

3. Profile auto-detection (by priority):
   - `LLM_CONFIG_PROFILE` environment variable (recommended)
   - `LLM_CONFIG_ENV` environment variable (backward compatibility)
   - `flashboot_core.env.Environment.get_active_profiles()` (if installed)
   - No profile activated by default

#### flashboot_core Integration

flashboot_core is an optional dependency, not required. Integration uses runtime detection:

```python
# pai_llm_config internal implementation
def _find_root() -> Path:
    # 1. Explicit environment variable
    if root := os.environ.get("LLM_CONFIG_ROOT"):
        return Path(root)

    # 2. flashboot_core (if available)
    try:
        from flashboot_core.utils import project_utils
        return Path(project_utils.get_project_root())
    except ImportError:
        pass

    # 3. Built-in fallback — walk up looking for marker files
    return _find_root_by_markers(Path.cwd())
```

This way, projects within the flashboot_core ecosystem automatically benefit from its smart root path discovery (git/svn/markers/structure), while standalone usage also works fine.

### 1.8 Global Singleton (Zero Boilerplate)

LLM configuration is used everywhere in a project; manually loading and passing the config object every time is tedious. A global singleton module provides one-line access:

```python
# ============================================================
# Use directly in any module, no manual loading needed
# ============================================================
from pai_llm_config import config

# L2 — Get clients
client = config.create_client("smart")                  # -> OpenAI(...) or Anthropic(...)
client = config.openai_client("smart")                  # -> OpenAI(...) (typed)
client = config.anthropic_client("claude-sonnet")       # -> anthropic.Anthropic(...)

# L1 — Get params (can be passed directly to any framework)
params = config.params("gpt4o")                         # -> dict
params = config.litellm_params("gpt4o")                 # -> dict (LiteLLM format)

# Also one-line integration with LangChain / DSPy:
# from langchain_openai import ChatOpenAI
# chat = ChatOpenAI(**config.params("smart"))

# Routing
model = config.route("code_generation")                 # -> ModelConfig

# Config info
config.list_models()
config.list_aliases()
```

#### Internal Mechanism

```python
# pai_llm_config/__init__.py
from pai_llm_config import LLMConfig

_config: LLMConfig | None = None

def _get_config() -> LLMConfig:
    global _config
    if _config is None:
        _config = LLMConfig.load()              # Auto-discover, loads on first access
    return _config

def client(name: str):
    return _get_config().create_client(name)

def openai_client(name: str):
    return _get_config().create_openai_client(name)

def params(name: str) -> dict:
    return _get_config().to_params(name)

# ... other methods follow the same pattern
```

Features:

- Lazy loading — config is loaded only on first call, zero import overhead
- Thread-safe — uses `threading.Lock` internally to protect initialization
- Resettable — `config.reload()` forces a reload (after config file changes)
- Overridable — `config.configure(instance)` manually injects an LLMConfig instance (for testing)

#### Comparison

```python
# Before: 3 lines, need to pass config object around
from pai_llm_config import LLMConfig
cfg = LLMConfig.load("llm-config.yaml", profile="production")
client = cfg.create_openai_client("smart")

# After: 1 line, use directly anywhere
from pai_llm_config import config
client = config.openai_client("smart")
```

---
