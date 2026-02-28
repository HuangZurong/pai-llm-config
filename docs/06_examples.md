# Usage Examples

## Quick Start

```yaml
# llm-config.yaml
version: "1"
providers:
  openai:
    type: openai
    api_key: ${OPENAI_API_KEY}
models:
  gpt-4o:
    provider: openai
    model: gpt-4o
aliases:
  smart: gpt-4o
```

```python
from pai_llm_config import config

response = config.openai_client("smart").chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)
print(response.choices[0].message.content)
```

---

## 1. Config Loading

### 1.1 LLMConfig.default() — Default Singleton (Recommended)

```python
from pai_llm_config import LLMConfig

# Process-wide cache, thread-safe, auto-discovers llm-config.yaml on first call
cfg = LLMConfig.default()
model = cfg.get("smart")
```

### 1.2 LLMConfig.load() — Custom Loading

```python
from pai_llm_config import LLMConfig

# Auto-discovery (creates a new instance each time)
cfg = LLMConfig.load()

# Explicit path
cfg = LLMConfig.load(config_path="config/llm-config.yaml")

# Specify profile (overrides LLM_CONFIG_PROFILE env var)
cfg = LLMConfig.load(profile="production")
```

### 1.3 config — Global Singleton

```python
from pai_llm_config import config

# config is a global singleton that auto-delegates to LLMConfig.default() on first access
# Provides shortcut access to all LLMConfig methods, no manual instance management needed
model = config.get("smart")
params = config.params("smart")
client = config.openai_client("smart")
```

```python
# Reload / inject (for switching environments or testing)
config.reload(profile="staging")

from pai_llm_config import LLMConfig
config.configure(LLMConfig({...}))  # Manual injection
```

---

## 2. Getting Model Config

```python
from pai_llm_config import config

# Get by model name
model = config.get("gpt-4o")
model.provider       # "openai"
model.model          # "gpt-4o"
model.temperature    # 0.7 (from defaults)
model.max_tokens     # 4096

# Get by alias (auto-resolved)
model = config.get("smart")  # Equivalent to config.get("gpt-4o")

# List all available models and aliases
config.list_models()    # ["gpt-4o", "claude-3-5-sonnet", "smart", "reasoning", ...]
config.list_aliases()   # {"smart": "gpt-4o", "reasoning": "claude-3-5-sonnet", ...}
```

---

## 3. L1: Parameter Output (Zero Extra Dependencies)

L1 layer only outputs dicts, with no SDK dependencies. Suitable for passing to OpenAI SDK, LangChain, DSPy, or any other framework.

### 3.1 OpenAI SDK Format

```python
from pai_llm_config import config
from openai import OpenAI

params = config.params("smart")
# -> {"model": "gpt-4o", "api_key": "sk-xxx", "base_url": "https://...", "temperature": 0.7, ...}

client = OpenAI(api_key=params.pop("api_key"), base_url=params.pop("base_url", None))
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Hello!"}],
    **params,
)
```

### 3.2 LiteLLM Format

```python
from pai_llm_config import config
import litellm

params = config.litellm_params("smart")
# -> {"model": "openai/gpt-4o", "api_key": "sk-xxx", "api_base": "https://...", ...}

response = litellm.completion(messages=[{"role": "user", "content": "Hello"}], **params)
```

### 3.3 DSPy Format

```python
from pai_llm_config import config
import dspy

params = config.dspy_params("smart")
# -> {"model": "openai/gpt-4o", "api_key": "sk-xxx", "api_base": "https://...", "temperature": 0.7, ...}

lm = dspy.LM(**params)
dspy.configure(lm=lm)
```

> **Note**: `params()` outputs `base_url` (OpenAI SDK format), while `litellm_params()` and `dspy_params()` output `api_base` + `provider/model` prefix. DSPy uses LiteLLM internally — always use `dspy_params()` instead of `params()`.

---

## 4. L2: SDK Client Factory

L2 layer returns real SDK client instances with built-in key rotation and usage tracking.

### 4.1 Typed Methods (Recommended)

```python
from pai_llm_config import config

# OpenAI
client = config.openai_client("smart")        # -> openai.OpenAI
response = client.chat.completions.create(
    model="gpt-4o",
    messages=[{"role": "user", "content": "Hello!"}],
)

# Anthropic
client = config.anthropic_client("reasoning")  # -> anthropic.Anthropic

# Async
async_client = config.async_openai_client("smart")      # -> openai.AsyncOpenAI
async_client = config.async_anthropic_client("reasoning") # -> anthropic.AsyncAnthropic
```

### 4.2 Auto-Dispatch

```python
from pai_llm_config import config

# Automatically returns the appropriate SDK client based on provider type
client = config.create_client("smart")          # -> openai.OpenAI
client = config.create_client("reasoning")      # -> anthropic.Anthropic
```

### 4.3 Streaming

```python
from pai_llm_config import config

# OpenAI streaming — auto-injects stream=True, reports usage when iteration ends
stream = config.stream_openai_chat("smart", messages=[{"role": "user", "content": "Tell a story"}])
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")

# Also supports with statement
with config.stream_openai_chat("smart", messages=[...]) as stream:
    for chunk in stream:
        print(chunk.choices[0].delta.content or "", end="")

# Anthropic streaming
with config.stream_anthropic_chat("reasoning", messages=[...], max_tokens=1024) as stream:
    for text in stream.text_stream:
        print(text, end="")

# Auto-dispatch (selects OpenAI or Anthropic streaming based on provider type)
stream = config.stream_chat("smart", messages=[...])

# Override model default parameters
stream = config.stream_openai_chat("smart", messages=[...], temperature=0.9, max_tokens=100)
```

---

## 5. Framework Integration

### 5.1 DSPy

```python
from pai_llm_config import config

# Option 1: dspy_client() one-step setup (recommended)
# Internally creates dspy.LM and calls dspy.configure(), returns the dspy module
dspy = config.dspy_client("smart")

# Use directly, no manual configure needed
qa = dspy.ChainOfThought("question -> answer")
result = qa(question="What is pai-llm-config?")
print(result.answer)

# Supports passing DSPy-specific parameters
dspy = config.dspy_client("smart", cache=False, num_retries=5)
```

```python
# Option 2: dspy_params() manual setup (more flexible)
from pai_llm_config import config
import dspy

lm = dspy.LM(**config.dspy_params("smart"))
dspy.configure(lm=lm)
```

> `dspy_params()` automatically adds the `provider/model` prefix and outputs `api_base`. Do not use `params()` to configure DSPy.

### 5.2 LangChain

```python
from pai_llm_config import config
from langchain_openai import ChatOpenAI

# params() outputs OpenAI SDK format, can be passed directly to LangChain
chat = ChatOpenAI(**config.params("smart"))
response = chat.invoke("Analyze the performance bottlenecks in this code")
```

### 5.3 LiteLLM

```python
from pai_llm_config import config

# Option 1: litellm_client() returns litellm.Router (recommended)
client = config.litellm_client("smart")
response = client.completion(model="smart", messages=[{"role": "user", "content": "Hello"}])

# Supports passing Router parameters
client = config.litellm_client("smart", routing_strategy="simple-shuffle")
```

```python
# Option 2: litellm_params() manual call (more flexible)
from pai_llm_config import config
import litellm

params = config.litellm_params("smart")
response = litellm.completion(messages=[{"role": "user", "content": "Hello"}], **params)
```

### 5.4 Gemini (via OpenAI-compatible endpoint)

```yaml
# llm-config.yaml
providers:
  google:
    type: openai
    api_key: ${GOOGLE_API_KEY}
    api_base: https://generativelanguage.googleapis.com/v1beta/openai/
models:
  gemini-flash:
    provider: google
    model: gemini-2.0-flash
```

```python
from pai_llm_config import config

# Usage is identical to OpenAI models
client = config.openai_client("gemini-flash")
response = client.chat.completions.create(
    model="gemini-2.0-flash",
    messages=[{"role": "user", "content": "Hello from Gemini!"}],
)
```

---

## 6. Advanced Features

### 6.1 Static Routing

```yaml
# llm-config.yaml
routing:
  presets:
    code_generation: smart
    summarization: cheap
    classification: cheap
```

```python
from pai_llm_config import config

model = config.route("code_generation")
print(model.model)  # "gpt-4o"

# Different tasks use different models
code_client = config.openai_client("smart")
summary_client = config.openai_client("cheap")
```

### 6.2 Key Rotation & Health Monitoring

```yaml
# llm-config.yaml
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
from pai_llm_config import LLMConfig

cfg = LLMConfig.default()

# L2 clients have built-in key rotation, completely transparent to business code
client = cfg.create_openai_client("gpt-4o")
for task in tasks:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": task}],
    )

# Check key pool status
pool = cfg.key_pool("openai")
print(pool.status())
# [
#   {"alias": "primary", "healthy": True, "available": True, "requests": 42, "tokens": 15000, "cost_usd": 0.038},
#   {"alias": "secondary", "healthy": True, "available": True, "requests": 0, "tokens": 0, "cost_usd": 0.0},
# ]

# Manual management
pool.report_success("sk-xxx", tokens=500, cost_usd=0.003)
pool.report_error("sk-xxx")    # Auto-marks unavailable after 3 consecutive errors
pool.reset_health()            # Reset all key health status
pool.reset_health("sk-xxx")    # Reset specific key
```
