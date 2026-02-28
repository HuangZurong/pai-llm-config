# Unified LLM Configuration Library

## Documentation Index

| Document | Content |
|------|------|
| [01_design.md](01_design.md) | Project background, problem statement, market landscape, requirements |
| [02_config-spec.md](02_config-spec.md) | Full YAML config file specification (Provider / Model / Alias / Profile) |
| [03_api-reference.md](03_api-reference.md) | Python API design (LLMConfig / Routing / Key Pool / Parameter Adapters) |
| [04_architecture.md](04_architecture.md) | Architecture design, class diagram, concurrency safety, key pool logic, semantic validation |
| [05_roadmap.md](05_roadmap.md) | Tech stack + version roadmap (this file) |
| [06_examples.md](06_examples.md) | Usage examples (basics, multi-model, DSPy, LangChain, LiteLLM, Gemini) |
| [07_mapping_guide.md](07_mapping_guide.md) | Model mapping & compatibility guide (Mappings mechanism, provider protocol boundaries) |

---

## 1. Tech Stack

| Component | Choice | Rationale |
| --- | --- | --- |
| Config model | Pydantic v2 | Type validation, serialization, IDE completion, mature ecosystem |
| File parsing | PyYAML + tomli | YAML/TOML dual support, covers mainstream formats |
| Environment variables | python-dotenv | Lightweight standard, widely used in the community |
| Variable substitution | Custom `${VAR}` parser | Simple, no extra dependencies |
| Usage storage | SQLite (default) | Zero deployment, single-machine persistence |
| Distributed storage | Redis (optional) | Multi-process/multi-instance sharing |
| Framework adapters | Plugin mode + extras | Install on demand, no forced dependency on any framework |
| CLI | click / typer | Rapid CLI tool development |

### Dependency Strategy

```toml
# pai-llm-config/pyproject.toml
[project]
name = "pai-llm-config"
dependencies = [
    "pydantic>=2.0",
    "pyyaml>=6.0",
    "python-dotenv>=1.0",
    "tomli>=2.0",
]

[project.optional-dependencies]
openai = ["openai>=1.0"]       # L2 OpenAI / OpenAI-compatible clients
anthropic = ["anthropic>=0.30"] # L2 Anthropic client
litellm = ["litellm>=1.0"]     # L2 LiteLLM unified client
redis = ["redis>=5.0"]
vault = ["hvac>=2.0"]           # HashiCorp Vault
aws = ["boto3>=1.34"]           # AWS Secrets Manager
all = ["pai-llm-config[openai,anthropic,litellm,redis,vault,aws]"]
```

---

## 2. Implementation Roadmap

### v0.1 — Functional (Core Config)

- [x] Pydantic data model definitions (Provider / Model / Alias)
- [x] YAML config file loading
- [x] `${VAR}` environment variable resolution
- [x] .env file loading
- [x] `config.get()` to retrieve model config by name/alias
- [x] Multi-environment support (profile overrides)
- [x] Global singleton `config` (lazy loading, thread-safe, resettable)
- [x] External name mappings (mappings)
- [x] Config file auto-discovery (llm-config.yaml/yml, including subdirectories)
- [x] flashboot_core integration (project root path, profile detection)
- [x] Semantic validation (provider references, alias conflicts, type checks)
- [x] Unit tests (194 tests)

### v0.2 — Usable (Parameter Adapters + Static Routing)

- [x] L1 config parameter output (to_params / to_litellm_params)
- [x] Default parameter merging logic (defaults -> model-level override, including top_p/stop/seed/response_format)
- [x] L2 client factory — OpenAI / OpenAI-compatible (create_client / create_async_client)
- [x] L2 client factory — Anthropic (create_anthropic_client / create_async_anthropic_client)
- [x] L2 client factory — LiteLLM unified client (create_litellm_client)
- [x] L2 Streaming support (stream=True, auto-reports usage after stream ends)
- [x] Static task routing (routing.presets)

### v0.3 — Multi-Key Pool

- [x] KeyPool manager
- [x] priority / round_robin / least_used / random strategies
- [x] In-memory usage tracking
- [x] Key health checks (error counting + auto-mark unavailable)
- [x] Single key / multi-key config compatibility
- [x] L2 client factory integrated key rotation hooks (auto key selection before calls, auto usage reporting after)
- [ ] Embedding model support (type: embedding, L2 wraps embeddings.create)

### v0.4 — Persistence + Budgets

- [ ] SQLite usage persistence
- [ ] Budget control (daily/monthly limits)
- [ ] Event callbacks (on_key_exhausted / on_budget_warning)

### v0.5 — Conditional Routing + Fallback

- [ ] Conditional rule routing (routing.rules)
- [ ] Fallback chains
- [ ] route_by() interface

### v0.6 — Intelligent Routing

- [ ] RouterStrategy plugin interface
- [ ] RouteLLM integration
- [ ] cost_optimized / quality_first / latency_first strategies
- [ ] smart_route() interface

### v0.7 — Polish

- [ ] CLI tools (init / validate / status)
- [ ] TOML config support
- [ ] Redis usage tracking backend
- [ ] Secret management integration (Vault / AWS SM)
- [ ] Hot reload
- [ ] Full documentation + PyPI publish

### v0.8 — Ecosystem Integration (LiteLLM Deep Binding)

- [ ] **LiteLLM Config Mirroring**: Export `LLMConfig` as LiteLLM Proxy `config.yaml` format.
- [ ] **Native Factory**: Implement `ModelConfig.to_litellm_params()` providing full parameter payload for `litellm.completion`.
- [ ] **Governance Callbacks**: Built-in LiteLLM observation callbacks that pump cost and usage back to `pai-llm-config` in real-time for alerting.
- [ ] **Unified Credential Injector**: Bridge secure provider credentials seamlessly into LiteLLM runtime context.
- [ ] **Zero-config Bridge**: Provide `pai_llm_config.integrations.litellm` module — import and directly use `completion` function with automatic mapping, alias, and governance hooks.
