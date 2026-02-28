# API 参考

## 1. API 设计

### 1.1 核心接口

```python
from pai_llm_config import LLMConfig
# 或者
from pai_llm_config import config

# 默认单例（推荐） — 全进程缓存，线程安全
cfg = LLMConfig.default()              # 首次调用自动加载 llm-config.yaml，后续返回缓存实例

# 加载配置 — 自动发现
cfg = LLMConfig.load()                     # 自动查找项目根目录下的 llm-config.yaml

# 加载配置 — 显式指定
cfg = LLMConfig.load(
    config_path="llm-config.yaml",  # 配置文件路径（可选，不传则自动发现）
    profile="production",         # Profile，默认读 LLM_CONFIG_PROFILE 环境变量
    dotenv=True,                  # 是否加载 .env 文件
)

# 重置单例（用于切换环境或测试）
LLMConfig.reset_default()

# 获取模型配置（按名称或别名）
model = cfg.get("gpt4o")
model = cfg.get("smart")      # 别名自动解析

model.provider                    # "openai-proxy"
model.model                       # "gpt-4o"
model.api_base                    # 代理到 Provider 的 api_base："https://prod-proxy.com/v1"
model.temperature                 # 0.3（模型级覆盖）
model.max_context                 # 128000
model.capabilities                # ["reasoning", "code", "vision", "function_calling"]
model.cost_per_1k_input           # 0.0025

# 批量获取
models = cfg.get_models(["smart", "fast", "cheap"])

# 列出所有可用模型和别名
cfg.list_models()              # ["gpt4o", "claude-sonnet", "deepseek-chat", "qwen-local"]
cfg.list_aliases()             # {"smart": "gpt4o", "fast": "deepseek-chat", ...}
```

### 1.2 路由接口

路由方法统一返回 `ModelConfig` 对象（与 `config.get()` 返回类型一致），可直接传给 `create_client()` 等方法。

```python
# 静态任务路由
model = config.route("code_generation")       # -> ModelConfig (gpt4o)
model = config.route("summarization")         # -> ModelConfig (deepseek-chat)
client = config.create_client(model)          # 接受 ModelConfig 或 str

# 条件路由
model = config.route_by(
    capabilities=["reasoning", "code"],
    prefer="cheapest",                         # cheapest / fastest / best
)

# Fallback
model = config.get_with_fallback("smart")     # gpt4o 不可用时自动降级

# 智能路由（P2）
model = config.smart_route(
    prompt="请帮我重构这段复杂的递归算法...",
    strategy="cost_optimized",
)
```

### 1.3 Key 池接口

```python
# 查看 Key 池状态
pool = config.key_pool("openai-proxy")
pool.status()

# 用量上报（框架适配器内部调用）
pool.report_usage(key="key1", tokens_in=500, tokens_out=200, cost=0.003)
pool.report_error(key="key3", error=RateLimitError("429"))

# 事件回调
config.on_key_exhausted(lambda key: notify(f"{key.alias} 额度用完"))
config.on_key_error(lambda key, err: log(f"{key.alias} 报错: {err}"))
config.on_budget_warning(lambda model, usage: alert(f"{model} 已用 {usage.percent}%"))
```

### 1.4 参数适配（两层设计）

适配器分两层，按需选择集成深度：

```
L1 — 配置参数（dict）     最轻量，零依赖，自己创建客户端，可直接传给 LangChain/DSPy 等框架
L2 — SDK 客户端工厂       返回原生 SDK 客户端，内置 Key 轮换 + 用量追踪
```

> **设计哲学**：不做 L3 框架适配器。L1 输出的参数可直接传给任何框架：
> ```python
> ChatOpenAI(**config.params("smart"))          # LangChain（OpenAI SDK 格式）
> dspy.LM(**config.dspy_params("smart"))        # DSPy（LiteLLM 格式）
> litellm.completion(**config.litellm_params("smart"), messages=[...])  # LiteLLM
> ```
> L2 层提供一步到位的便捷方法：`config.dspy_client("smart")` 返回已配置的 `dspy` 模块，`config.litellm_client("smart")` 返回 `litellm.Router`。
> 维护框架适配器 = 版本耦合 + API 追赶 + 导入膨胀，收益极低。

#### L1 — 配置参数输出（零额外依赖）

`to_params()` 根据 provider 的 `type` 输出对应 SDK 的参数格式：

```python
# OpenAI-compatible provider
params = config.to_params("gpt4o")
# -> {
#     "model": "gpt-4o",
#     "api_key": "sk-xxx",          # 自动从 Key 池选择
#     "base_url": "https://proxy.com/v1",
#     "temperature": 0.3,
#     "max_tokens": 2048,
# }
from openai import OpenAI
client = OpenAI(**params)

# Anthropic provider — 输出 Anthropic SDK 参数格式
params = config.to_params("claude-sonnet")
# -> {
#     "model": "claude-sonnet-4-20250514",
#     "api_key": "sk-ant-xxx",
#     "max_tokens": 2048,            # Anthropic SDK 必填
# }
from anthropic import Anthropic
client = Anthropic(api_key=params.pop("api_key"))

# LiteLLM 统一格式（屏蔽 provider 差异）
params = config.to_litellm_params("gpt4o")
# -> {"model": "openai/gpt-4o", "api_key": "sk-xxx", "api_base": "https://...", ...}
import litellm
response = litellm.completion(messages=[...], **params)
```

#### L2 — SDK 客户端工厂（内置 Key 轮换 + 用量追踪）

`create_client()` 根据 provider type 返回不同 SDK 客户端。为了类型安全，提供类型化的工厂方法：

```python
# 通用方法 — 返回 Union[OpenAI, anthropic.Anthropic]，需要自行判断类型
client = config.create_client("smart")

# 类型化方法（推荐）— IDE 补全完整，返回类型确定
from openai import OpenAI, AsyncOpenAI
client: OpenAI = config.create_openai_client("smart")
async_client: AsyncOpenAI = config.create_async_openai_client("smart")

import anthropic
client: anthropic.Anthropic = config.create_anthropic_client("claude-sonnet")
async_client: anthropic.AsyncAnthropic = config.create_async_anthropic_client("claude-sonnet")

# 如果 provider type 与方法不匹配，抛出 ProviderTypeMismatchError
# 例如：config.create_openai_client("claude-sonnet") -> ProviderTypeMismatchError

# LiteLLM 客户端（返回 litellm.Router，统一接口调用任意模型）
client = config.litellm_client("smart")
response = client.completion(model="smart", messages=[...])

# DSPy 客户端（返回已配置的 dspy 模块，直接使用）
dspy = config.dspy_client("smart")
qa = dspy.ChainOfThought("question -> answer")
```

#### L2 客户端工厂内部机制

通过自定义 httpx Transport 层拦截请求，避免 monkey-patch 破坏类型安全：

```python
import httpx
from openai import OpenAI

class KeyRotationTransport(httpx.BaseTransport):
    """在 HTTP 层拦截请求，注入 Key 轮换和用量上报。

    优势：
    - 不修改 SDK 对象的任何方法，类型安全完整保留
    - 所有 SDK 方法（chat、embeddings、with_options 等）自动受控
    - 对 streaming 和非 streaming 请求统一处理
    """

    def __init__(self, key_pool: KeyPool, model_config: ModelConfig):
        self._key_pool = key_pool
        self._model_config = model_config
        self._inner = httpx.HTTPTransport()

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        # 每次请求前按策略选 Key，注入 Authorization header
        current_key = self._key_pool.get_key()
        request.headers["Authorization"] = f"Bearer {current_key}"

        try:
            response = self._inner.handle_request(request)
            # 从响应中提取 usage 并上报（非 streaming 场景）
            self._report_usage_if_available(response, current_key)
            return response
        except Exception as e:
            self._key_pool.report_error(key=current_key, error=e)
            raise

    def _report_usage_if_available(self, response: httpx.Response, key: str):
        # 解析响应 body 中的 usage 字段，上报用量
        ...


# 工厂方法内部逻辑
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
        api_key="placeholder",           # 实际 Key 由 transport 注入
        base_url=provider.api_base,
        http_client=httpx.Client(transport=transport),
    )
```

Anthropic SDK 同样基于 httpx，使用相同的 Transport 拦截机制。

> **设计决策**：选择 httpx Transport 而非 monkey-patch 的原因：
>
> 1. 类型安全 — SDK 对象的所有方法签名不变，IDE 补全完整
> 2. 全覆盖 — 所有 API 调用（chat、embeddings、files 等）自动经过 transport
> 3. 可组合 — 可叠加重试、日志、metrics 等多个 transport 层
> 4. streaming 友好 — 在 HTTP 层统一处理，无需分别 patch sync/async/streaming 方法

### 1.5 预算接口

```python
config.budget.usage_today()                   # 今日全局用量
config.budget.usage_today("gpt4o")            # 今日某模型用量
config.budget.remaining("gpt4o")              # 今日剩余额度
config.budget.usage_monthly()                 # 本月用量
```

---

