# Design Background & Requirements Specification

## 1. Background

### 1.1 Problem Statement

Current LLM application development faces the following pain points in configuration management:

#### Configuration & Environment Management

| Pain Point | Description | Solution |
| --- | --- | --- |
| Fragmented configuration | Each framework has its own configuration approach; developers repeatedly handle the same logic | F01 Multi-source config loading + F07 Parameter adapters: one YAML config, `to_params()` outputs SDK-specific formats |
| Tedious environment switching | Switching between dev/test/prod requires manual config handling | F03 Multi-environment support + F17 Config inheritance: profile override mechanism, one-click switching |
| No team config standard | Which model and what parameters to use is shared via word-of-mouth or wiki, with no version-controlled, reviewable standard config file | YAML config files are naturally Git-versioned; `${VAR}` references separate secrets from config, teams share config structure not secrets |

#### SDK Integration

| Pain Point | Description | Solution |
| --- | --- | --- |
| Excessive SDK glue code | After getting config, you still need to manually create OpenAI/Anthropic clients, handle key injection, usage reporting — repeated in every project | F23 Client factory: `config.create_client("smart")` directly returns an SDK client with key rotation and usage tracking |
| High framework switching cost | Switching from OpenAI SDK to LiteLLM, or LangChain to DSPy, requires rewriting client creation and call logic | F07 Two-layer adapters: L1 config params output -> L2 client factory, `to_params()` can be passed directly to any framework |
| Key rotation disconnected from SDK | Key pool management and SDK calls are two separate systems; developers must select keys before calls and report usage after | L2 client factory has built-in key rotation hooks, automatically selects keys and reports usage, completely transparent to business code |

#### Secrets & Security

| Pain Point | Description | Solution |
| --- | --- | --- |
| Disorganized secret management | API keys scattered across code, env vars, and config files without unified management | F04 Secret safety: `${ENV_VAR}` references + .env loading, secrets never stored in config files; P2 integrates Vault / AWS SM |
| Missing multi-key rotation | In proxy API scenarios, one model maps to multiple keys (rotated by quota/rate), no ready-made solution | F08-F11 Multi-key pool: KeyPool automatically manages key selection, rotation, and health checks, completely transparent to business code |

#### Model Management

| Pain Point | Description | Solution |
| --- | --- | --- |
| Difficult multi-model coordination | A system using multiple models (by capability/price/scenario) lacks unified model registry and routing | F06 Model aliases + F12/F13 Routing: semantic aliases (smart/fast/cheap) + static preset/conditional rule routing |
| High model migration cost | Providers frequently deprecate models (gpt-4-turbo -> gpt-4o, claude-3 -> claude-4); when config is scattered in code, every migration is a global search-and-replace | F06 Model aliases: business code only references aliases (smart), model migration only changes the YAML alias target, zero code changes |
| Provider lock-in | Business code directly couples to a specific provider's SDK/parameter format; switching from OpenAI to DeepSeek or Anthropic requires code changes | F02 Unified multi-provider abstraction + F07 Framework adapters: unified config format abstracts provider differences, switching providers only changes config |
| Scattered model capability info | Choosing a model requires checking each provider's docs for context window, vision/function calling support, etc. — no unified capability registry | Model config fields (capabilities / max_context / cost / latency_tier) form a unified capability registry; conditional routing can select models based on this metadata |

#### Cost & Observability

| Pain Point | Description | Solution |
| --- | --- | --- |
| Invisible costs | When using multiple models in parallel, you don't know where money is going, which task is most expensive, which key is near its limit — surprises come at billing time | F10 Key usage tracking + F15 Budget control: track usage by key/model/global dimensions, supports daily/monthly limits and event callbacks |

### 1.2 Market Landscape

| Project | Positioning | Limitation |
| --- | --- | --- |
| Dynaconf | General config management | Not LLM-specific, no model routing/key pool concepts |
| LiteLLM | LLM call gateway | Focused on runtime, config management not elegant |
| LiteLLM Router | Load balancing | Rule-based, lacks intelligent routing |
| RouteLLM (LMSys) | Intelligent routing | Only does routing, no config management |
| Portkey AI | API gateway | Closed-source SaaS, cannot self-host |
| Unify AI / Not Diamond | Intelligent routing | Closed-source API services |

### 1.3 Project Positioning

pai-llm-config is an **LLM-native configuration management library** with the core philosophy:

> One YAML describes all model capabilities and costs; business code only says "what I want to do", and the library decides "which model and which key to use".

### 1.4 Package Relationship Design

pai-llm-config is published as a standalone package, with transparent re-export through pai-llm so users don't need to be aware of the underlying split.

```
pai-llm (main package, user-facing entry)
├── pai_llm.config          →  Re-exported from pai_llm_config
├── pai_llm.conversation    →  Conversation history management (existing)
├── pai_llm.prompt          →  Prompt Hub (planned)
└── ...

pai-llm-config (standalone package, separate repo, independent versioning)
└── pai_llm_config/
    ├── __init__.py          →  LLMConfig, ModelConfig, ...
    ├── config.py
    ├── models.py
    └── ...
```

#### Installation

```bash
# Option 1: Install config only (lightweight, no dependency on other pai-llm features)
pip install pai-llm-config

# Option 2: Install pai-llm, which automatically includes config (recommended, all-in-one)
pip install pai-llm[config]
# Or the full bundle
pip install pai-llm[all]
```

#### Import

```python
# Option 1: Import directly from the standalone package (explicit, unambiguous)
from pai_llm_config import LLMConfig

# Option 2: Import via pai-llm re-export (more user-friendly, one package name)
from pai_llm_config import LLMConfig

# Both are completely equivalent, returning the same class
```

#### pai-llm Side Implementation

```python
# pai_llm/config/__init__.py — transparent re-export
try:
    from pai_llm_config import *           # noqa: F401,F403
    from pai_llm_config import LLMConfig   # explicit export for IDE completion
except ImportError:
    raise ImportError(
        "pai-llm-config is required for config features. "
        "Install it with: pip install pai-llm[config] or pip install pai-llm-config"
    )
```

```toml
# pai-llm/pyproject.toml
[project.optional-dependencies]
config = ["pai-llm-config>=0.1"]
all = ["pai-llm[config]"]
```

#### Design Principles

- pai-llm-config has zero dependency on pai-llm and can be used completely standalone
- pai-llm provides transparent access via optional dependency + re-export
- Users only need to remember `from pai_llm_config import LLMConfig`, no need to know which underlying package
- Future pai-llm companion libraries (e.g., pai-llm-prompt, pai-llm-agent) can use the same pattern

### 1.5 Key Differentiators

1. **LLM-native** — Configuration format designed for LLM scenarios, works out of the box
2. **Framework bridging** — One config, outputs in each SDK's parameter format (OpenAI / Anthropic / LiteLLM), also directly usable with LangChain, DSPy, etc.
3. **Model aliases + routing** — Business code only cares about semantics (smart/fast), not specific models
4. **Multi-key pool** — Automatic rotation, quota tracking, health checks
5. **Progressive integration** — L1 pure config with zero intrusion, L2 optionally takes over client creation; `to_params()` can be directly passed to LangChain, DSPy, or any other framework

### 1.6 Compatibility Analysis

#### Provider Coverage

| Provider Type | Representatives | L2 Support | Coverage |
| --- | --- | --- | --- |
| OpenAI-compatible | OpenAI, Azure, DeepSeek, Moonshot, Zhipu, Yi, Ollama, vLLM, various proxies | Direct OpenAI client support | Strong |
| Anthropic | Claude series | Native Anthropic client | Strong |
| Google | Gemini series | OpenAI-compatible mode (`type: openai` + Google's official OpenAI-compatible endpoint) | Strong |
| AWS Bedrock | Claude/Llama/Mistral via AWS | LiteLLM client fallback | Medium |
| Mistral | Mistral official API | OpenAI-compatible mode available | Medium |
| Others | Cohere, AI21, etc. | LiteLLM client fallback (supports 100+ providers) | Medium |

Strategy: L2 native clients cover OpenAI-compatible + Anthropic (~80% of scenarios); Google Gemini via official OpenAI-compatible endpoint also falls under OpenAI-compatible; LiteLLM client covers all remaining providers.

#### Framework Coverage

| Framework | Support Level | Priority |
| --- | --- | --- |
| OpenAI SDK | L2 client factory | P0 |
| Anthropic SDK | L2 client factory | P0 |
| LiteLLM | L1 params + L2 client | P0 |

#### API Pattern Coverage

| API Pattern | Support | Priority |
| --- | --- | --- |
| Chat Completions | L2 wraps `chat.completions.create` / `messages.create` | P0 |
| Streaming | L2 wraps stream=True, usage reported after stream ends | P0 |
| Async | `create_async_client()` | P0 |
| Embeddings | Model config `type: embedding`, L2 wraps `embeddings.create` | P1 |
| Image Generation | Not covered | — |
| Audio (TTS/STT) | Not covered | — |
| Tool/Function Calling | Capabilities metadata, no special handling needed | — |

#### SDK API Shape Differences

Different providers have different SDK API shapes; the L2 client factory wraps each provider type separately:

```python
# OpenAI-compatible — wraps chat.completions.create
client = config.create_client("gpt4o")
response = client.chat.completions.create(messages=[...])
# Returns native OpenAI client, API shape unchanged

# Anthropic — wraps messages.create
client = config.create_client("claude-sonnet")
response = client.messages.create(max_tokens=1024, messages=[...])
# Returns native Anthropic client, API shape unchanged

# LiteLLM — unified interface, abstracts all differences
client = config.litellm_client("smart")
response = client.completion(model="smart", messages=[...])
# Regardless of underlying provider (OpenAI/Anthropic/Gemini), call pattern is unified
```

Design principle: L2 does not change the SDK's API shape, only injects key rotation and usage tracking internally. The client users receive is identical to using the native SDK directly — IDE completion and type hints fully preserved. If a unified API shape is needed, use the LiteLLM client.

## 2. Requirements Specification

### 2.1 P0 — Core Features (v0.1 ~ v0.2)

| ID | Requirement | Description |
| --- | --- | --- |
| F01 | Multi-source config loading | Support .env, env vars, YAML/TOML files, with controllable priority |
| F02 | Unified multi-provider abstraction | OpenAI, Anthropic, Azure, local models (Ollama/vLLM), domestic proxies — unified config format |
| F03 | Multi-environment support | One-click switching between dev / staging / prod |
| F04 | Secret safety | Support `${ENV_VAR}` references, .env loading; secrets never stored in config files |
| F05 | Type validation | Config items have explicit types, validated at load time, errors exposed early |
| F06 | Model aliases | Define semantic aliases like smart, fast, cheap mapping to specific models |
| F07 | Parameter adapter output | Two-layer adapters: L1 config param dict -> L2 SDK client factory (OpenAI / Anthropic / LiteLLM) |
| F23 | Client factory | `create_client()` directly returns SDK client instances with key rotation and usage tracking |
| F24 | Streaming support | L2 client wraps stream=True mode, automatically reports usage after stream ends |

### 2.2 P1 — Enhanced Features (v0.3 ~ v0.5)

| ID | Requirement | Description |
| --- | --- | --- |
| F08 | Multi-key pool | One provider with multiple API keys, automatically selected by strategy |
| F09 | Key selection strategies | Support priority / round_robin / least_used / random |
| F10 | Key usage tracking | Track each key's usage (tokens/cost/request count) |
| F11 | Key health checks | Auto-mark unavailable after consecutive errors, periodic recovery probing |
| F12 | Static task routing | Map task types to models via preset rules |
| F13 | Conditional routing | Dynamically select models based on token count, capabilities, etc. |
| F14 | Fallback chains | Automatically degrade along a chain when primary model is unavailable |
| F15 | Budget control | Set daily/monthly cost limits per model/globally |
| F16 | Default parameters | temperature, max_tokens, etc. can be set per model/globally |
| F17 | Config inheritance | Child environments inherit parent config, only override differences |
| F25 | Embedding model support | Model config supports `type: embedding`, L2 wraps `embeddings.create` |

### 2.3 P2 — Advanced Features (v0.6 ~ v0.7)

| ID | Requirement | Description |
| --- | --- | --- |
| F18 | Intelligent routing | Auto-select optimal model based on prompt complexity (integrate RouteLLM or custom classifier) |
| F19 | CLI tools | `pai-llm-config init` generates templates, `pai-llm-config validate` validates config |
| F20 | Secret management integration | AWS Secrets Manager / Azure Key Vault / HashiCorp Vault |
| F21 | Hot reload | Runtime config changes without restart |
| F22 | Distributed usage tracking | Redis backend, supports multi-process/multi-instance shared usage data |
