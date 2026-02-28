# 使用示例

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

## 1. 配置加载

### 1.1 LLMConfig.default() — 默认单例（推荐）

```python
from pai_llm_config import LLMConfig

# 全进程缓存、线程安全，首次调用自动发现 llm-config.yaml
cfg = LLMConfig.default()
model = cfg.get("smart")
```

### 1.2 LLMConfig.load() — 自定义加载

```python
from pai_llm_config import LLMConfig

# 自动发现（每次新建实例）
cfg = LLMConfig.load()

# 显式指定路径
cfg = LLMConfig.load(config_path="config/llm-config.yaml")

# 指定 Profile（覆盖环境变量 LLM_CONFIG_PROFILE）
cfg = LLMConfig.load(profile="production")
```

### 1.3 config — 全局单例

```python
from pai_llm_config import config

# config 是全局单例，首次访问时自动委托 LLMConfig.default()
# 提供所有 LLMConfig 方法的快捷访问，无需手动管理实例
model = config.get("smart")
params = config.params("smart")
client = config.openai_client("smart")
```

```python
# 重载 / 注入（用于切换环境或测试）
config.reload(profile="staging")

from pai_llm_config import LLMConfig
config.configure(LLMConfig({...}))  # 手动注入
```

---

## 2. 获取模型配置

```python
from pai_llm_config import config

# 按模型名获取
model = config.get("gpt-4o")
model.provider       # "openai"
model.model          # "gpt-4o"
model.temperature    # 0.7 (来自 defaults)
model.max_tokens     # 4096

# 按别名获取（自动解析）
model = config.get("smart")  # 等价于 config.get("gpt-4o")

# 列出所有可用模型和别名
config.list_models()    # ["gpt-4o", "claude-3-5-sonnet", "smart", "reasoning", ...]
config.list_aliases()   # {"smart": "gpt-4o", "reasoning": "claude-3-5-sonnet", ...}
```

---

## 3. L1: 参数输出（零额外依赖）

L1 层只输出 dict，不依赖任何 SDK。适合传给 OpenAI SDK、LangChain、DSPy 等任何框架。

### 3.1 OpenAI SDK 格式

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

### 3.2 LiteLLM 格式

```python
from pai_llm_config import config
import litellm

params = config.litellm_params("smart")
# -> {"model": "openai/gpt-4o", "api_key": "sk-xxx", "api_base": "https://...", ...}

response = litellm.completion(messages=[{"role": "user", "content": "Hello"}], **params)
```

### 3.3 DSPy 格式

```python
from pai_llm_config import config
import dspy

params = config.dspy_params("smart")
# -> {"model": "openai/gpt-4o", "api_key": "sk-xxx", "api_base": "https://...", "temperature": 0.7, ...}

lm = dspy.LM(**params)
dspy.configure(lm=lm)
```

> **区别**：`params()` 输出 `base_url`（OpenAI SDK 格式），`litellm_params()` 和 `dspy_params()` 输出 `api_base` + `provider/model` 前缀。DSPy 底层使用 LiteLLM，请始终使用 `dspy_params()` 而非 `params()`。

---

## 4. L2: SDK 客户端工厂

L2 层返回真实 SDK 客户端实例，内置 Key 轮换和用量追踪。

### 4.1 类型化方法（推荐）

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

# 异步
async_client = config.async_openai_client("smart")      # -> openai.AsyncOpenAI
async_client = config.async_anthropic_client("reasoning") # -> anthropic.AsyncAnthropic
```

### 4.2 自动分派

```python
from pai_llm_config import config

# 根据 provider type 自动返回对应 SDK 客户端
client = config.create_client("smart")          # -> openai.OpenAI
client = config.create_client("reasoning")      # -> anthropic.Anthropic
```

### 4.3 流式调用

```python
from pai_llm_config import config

# OpenAI 流式 — 自动注入 stream=True，迭代结束自动上报用量
stream = config.stream_openai_chat("smart", messages=[{"role": "user", "content": "讲个故事"}])
for chunk in stream:
    print(chunk.choices[0].delta.content or "", end="")

# 也支持 with 语句
with config.stream_openai_chat("smart", messages=[...]) as stream:
    for chunk in stream:
        print(chunk.choices[0].delta.content or "", end="")

# Anthropic 流式
with config.stream_anthropic_chat("reasoning", messages=[...], max_tokens=1024) as stream:
    for text in stream.text_stream:
        print(text, end="")

# 自动分派（根据 provider type 选择 OpenAI 或 Anthropic 流式）
stream = config.stream_chat("smart", messages=[...])

# 覆盖模型默认参数
stream = config.stream_openai_chat("smart", messages=[...], temperature=0.9, max_tokens=100)
```

---

## 5. 框架集成

### 5.1 DSPy

```python
from pai_llm_config import config

# 方式一：dspy_client() 一步到位（推荐）
# 内部自动创建 dspy.LM 并调用 dspy.configure()，返回 dspy 模块
dspy = config.dspy_client("smart")

# 直接使用，无需手动 configure
qa = dspy.ChainOfThought("question -> answer")
result = qa(question="什么是 pai-llm-config？")
print(result.answer)

# 支持传入 DSPy 特有参数
dspy = config.dspy_client("smart", cache=False, num_retries=5)
```

```python
# 方式二：dspy_params() 手动构建（更灵活）
from pai_llm_config import config
import dspy

lm = dspy.LM(**config.dspy_params("smart"))
dspy.configure(lm=lm)
```

> `dspy_params()` 自动添加 `provider/model` 前缀并输出 `api_base`，请勿使用 `params()` 配置 DSPy。

### 5.2 LangChain

```python
from pai_llm_config import config
from langchain_openai import ChatOpenAI

# params() 输出 OpenAI SDK 格式，可直接传给 LangChain
chat = ChatOpenAI(**config.params("smart"))
response = chat.invoke("帮我分析这段代码的性能瓶颈")
```

### 5.3 LiteLLM

```python
from pai_llm_config import config

# 方式一：litellm_client() 返回 litellm.Router（推荐）
client = config.litellm_client("smart")
response = client.completion(model="smart", messages=[{"role": "user", "content": "Hello"}])

# 支持传入 Router 参数
client = config.litellm_client("smart", routing_strategy="simple-shuffle")
```

```python
# 方式二：litellm_params() 手动调用（更灵活）
from pai_llm_config import config
import litellm

params = config.litellm_params("smart")
response = litellm.completion(messages=[{"role": "user", "content": "Hello"}], **params)
```

### 5.4 Gemini（通过 OpenAI-compatible 端点）

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

# 和 OpenAI 模型用法完全一致
client = config.openai_client("gemini-flash")
response = client.chat.completions.create(
    model="gemini-2.0-flash",
    messages=[{"role": "user", "content": "Hello from Gemini!"}],
)
```

---

## 6. 高级功能

### 6.1 静态路由

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

# 不同任务用不同模型
code_client = config.openai_client("smart")
summary_client = config.openai_client("cheap")
```

### 6.2 Key 轮换与健康监控

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

# L2 客户端内置 Key 轮换，业务代码完全无感知
client = cfg.create_openai_client("gpt-4o")
for task in tasks:
    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[{"role": "user", "content": task}],
    )

# 查看 Key 池状态
pool = cfg.key_pool("openai")
print(pool.status())
# [
#   {"alias": "primary", "healthy": True, "available": True, "requests": 42, "tokens": 15000, "cost_usd": 0.038},
#   {"alias": "secondary", "healthy": True, "available": True, "requests": 0, "tokens": 0, "cost_usd": 0.0},
# ]

# 手动管理
pool.report_success("sk-xxx", tokens=500, cost_usd=0.003)
pool.report_error("sk-xxx")    # 连续 3 次 error 后自动标记不可用
pool.reset_health()            # 重置所有 key 健康状态
pool.reset_health("sk-xxx")    # 重置指定 key
```
