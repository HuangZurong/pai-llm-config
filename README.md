# pai-llm-config

[![PyPI version](https://img.shields.io/pypi/v/pai-llm-config.svg)](https://pypi.org/project/pai-llm-config/)
[![Python](https://img.shields.io/pypi/pyversions/pai-llm-config.svg)](https://pypi.org/project/pai-llm-config/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![GitHub stars](https://img.shields.io/github/stars/HuangZurong/pai-llm-config?style=social)](https://github.com/HuangZurong/pai-llm-config)

Unified configuration management for LLM applications.

One YAML file to manage all your LLM providers, models, API keys, and parameters. Works with OpenAI, Anthropic, Azure, LiteLLM, DSPy, LangChain, and more.

> If this project helps you, please consider giving it a star. It helps others discover it too.

## Features

- **Multi-provider** — OpenAI, Anthropic, Azure, LiteLLM, and any OpenAI-compatible endpoint (DeepSeek, Gemini, Ollama, vLLM, etc.)
- **Two-layer adapters** — L1 outputs plain dicts (zero extra deps), L2 returns real SDK clients with key rotation
- **Model aliases** — Reference models by semantic names (`smart`, `fast`, `cheap`) instead of `gpt-4o`
- **Multi-key pool** — Automatic key rotation with priority / round_robin / least_used / random strategies
- **Framework integration** — One-step client creation for DSPy, LiteLLM; params output for LangChain, OpenAI SDK, etc.
- **Streaming** — Built-in streaming wrappers with automatic usage reporting (OpenAI + Anthropic, sync + async)
- **Multi-environment** — Profile-based config (dev / staging / prod) with inheritance
- **Type-safe** — Pydantic validation, full IDE autocompletion

## Install

```bash
pip install pai-llm-config

# With optional SDK support
pip install pai-llm-config[openai]       # OpenAI SDK
pip install pai-llm-config[anthropic]    # Anthropic SDK
pip install pai-llm-config[litellm]      # LiteLLM
pip install pai-llm-config[all]          # Everything
```

## Quick Start

**1. Create `llm-config.yaml` in your project root:**

```yaml
version: "1"
providers:
  openai:
    type: openai
    api_key: ${OPENAI_API_KEY}
models:
  gpt-4o:
    provider: openai
    model: gpt-4o
    temperature: 0.7
    max_tokens: 4096
aliases:
  smart: gpt-4o
```

**2. Use it:**

```python
from pai_llm_config import config

# L2: One-line client creation with key rotation
client = config.openai_client("smart")
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

## Usage

### Config Loading

```python
from pai_llm_config import LLMConfig, config

# Global singleton (recommended) — auto-discovers llm-config.yaml
model = config.get("smart")

# Or use LLMConfig directly
cfg = LLMConfig.default()          # Cached singleton
cfg = LLMConfig.load()             # Fresh instance
cfg = LLMConfig.load(profile="production", config_path="config/llm.yaml")
```

### L1: Parameter Output (Zero Extra Dependencies)

```python
from pai_llm_config import config

# OpenAI SDK format
params = config.params("smart")
# -> {"model": "gpt-4o", "api_key": "sk-xxx", "base_url": "https://...", "temperature": 0.7, ...}

# LiteLLM format (provider/model prefix + api_base)
params = config.litellm_params("smart")
# -> {"model": "openai/gpt-4o", "api_key": "sk-xxx", "api_base": "https://...", ...}

# DSPy format
params = config.dspy_params("smart")
# -> {"model": "openai/gpt-4o", "api_key": "sk-xxx", "api_base": "https://...", ...}
```

### L2: SDK Client Factory

```python
from pai_llm_config import config

# Type-safe client creation with built-in key rotation
client = config.openai_client("smart")              # -> openai.OpenAI
client = config.anthropic_client("reasoning")        # -> anthropic.Anthropic
client = config.async_openai_client("smart")         # -> openai.AsyncOpenAI
client = config.async_anthropic_client("reasoning")  # -> anthropic.AsyncAnthropic

# Auto-dispatch by provider type
client = config.create_client("smart")               # -> openai.OpenAI or anthropic.Anthropic
```

### Framework Integration

```python
from pai_llm_config import config

# DSPy — one step, returns configured dspy module
dspy = config.dspy_client("smart")
qa = dspy.ChainOfThought("question -> answer")
result = qa(question="What is pai-llm-config?")

# LiteLLM — returns litellm.Router
client = config.litellm_client("smart")
response = client.completion(model="smart", messages=[...])

# LangChain — use params() output
from langchain_openai import ChatOpenAI
chat = ChatOpenAI(**config.params("smart"))
```

### Streaming

```python
from pai_llm_config import config

# OpenAI streaming with automatic usage reporting
stream = config.stream_openai_chat("smart", messages=[{"role": "user", "content": "Tell a story"}])
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")

# Anthropic streaming
with config.stream_anthropic_chat("reasoning", messages=[...], max_tokens=1024) as stream:
    for text in stream.text_stream:
        print(text, end="")

# Auto-dispatch
stream = config.stream_chat("smart", messages=[...])
```

### Multi-Key Rotation

```yaml
providers:
  openai:
    type: openai
    api_keys:
      - key: ${OPENAI_KEY_1}
        alias: "primary"
        priority: 1
        daily_limit_usd: 5.0
      - key: ${OPENAI_KEY_2}
        alias: "secondary"
        priority: 2
        daily_limit_usd: 10.0
    key_strategy: priority  # priority | round_robin | least_used | random
```

```python
# L2 clients automatically rotate keys — zero code changes
client = config.openai_client("smart")

# Monitor key pool health
pool = config.key_pool("openai")
print(pool.status())
```

### Task Routing

```yaml
routing:
  presets:
    code_generation: smart
    summarization: cheap
    classification: cheap
```

```python
model = config.route("code_generation")  # -> ModelConfig for "smart"
```

## Configuration Reference

See [docs/02_config-spec.md](docs/02_config-spec.md) for the full YAML specification, and [docs/06_examples.md](docs/06_examples.md) for more usage examples.

## Contributing

Contributions are welcome! Feel free to open issues or submit pull requests.

If you find this project useful, please give it a star on GitHub — it motivates continued development and helps others find this project.

## License

MIT
