# 配置文件规范

## 1. 配置文件设计

### 1.1 完整配置示例

```yaml
version: "1"

# ============================================================
# 全局默认参数
# temperature: 0.0 ~ 2.0, top_p: 0.0 ~ 1.0
# ============================================================
defaults:
  temperature: 0.7
  max_tokens: 2048
  timeout: 30

# ============================================================
# Provider 配置
# ============================================================
providers:
  # --- 单 Key（简写） ---
  anthropic:
    type: anthropic # anthropic SDK 原生协议
    api_key: ${ANTHROPIC_API_KEY}

  # --- 多 Key 池 ---
  openai-proxy:
    type: openai # OpenAI-compatible 协议
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

    key_strategy: priority # provider 级默认策略

  # --- Azure ---
  azure:
    type: azure # Azure OpenAI 协议
    api_key: ${AZURE_API_KEY}
    api_base: https://my-resource.openai.azure.com
    api_version: "2024-02-01"

  # --- DeepSeek ---
  deepseek:
    type: openai # DeepSeek 兼容 OpenAI 协议
    api_key: ${DEEPSEEK_API_KEY}
    api_base: https://api.deepseek.com/v1

  # --- 本地模型 ---
  local:
    type: openai # Ollama 兼容 OpenAI 协议
    api_base: http://localhost:11434

  # --- Google Gemini（通过 OpenAI-compatible 端点） ---
  google:
    type: openai # Google 提供官方 OpenAI 兼容端点
    api_key: ${GOOGLE_API_KEY}
    api_base: https://generativelanguage.googleapis.com/v1beta/openai/

# ============================================================
# 模型注册
# cost_per_1k_input / cost_per_1k_output 可省略，库内置主流模型
# 的默认价格表（定期更新）。用户配置的值优先于内置默认值。
# ============================================================
models:
  gpt4o:
    provider: openai-proxy
    model: gpt-4o
    # cost_per_1k_input / cost_per_1k_output 省略，使用内置默认值
    max_context: 128000
    capabilities: [reasoning, code, vision, function_calling]
    latency_tier: medium # low / medium / high
    temperature: 0.3 # 覆盖全局默认值
    key_strategy: priority # 模型级覆盖 provider 的 key_strategy（贵模型优先用高优先级 Key）

  claude-sonnet:
    provider: anthropic
    model: claude-sonnet-4-20250514
    max_context: 200000
    capabilities: [reasoning, code, function_calling]
    latency_tier: medium

  deepseek-chat:
    provider: deepseek
    model: deepseek-chat
    cost_per_1k_input: 0.0001 # 非主流模型需手动配置价格
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

  # --- Embedding 模型 ---
  text-embedding-3:
    provider: openai-proxy
    model: text-embedding-3-small
    type: embedding # 标记为 embedding 模型
    cost_per_1k_input: 0.00002
    dimensions: 1536
    max_context: 8191

# ============================================================
# 语义别名
# ============================================================
aliases:
  smart: gpt4o
  fast: deepseek-chat
  cheap: qwen-local
  balanced: claude-sonnet

# ============================================================
# 任务路由
# ============================================================
routing:
  # 静态预设
  presets:
    code_generation: smart
    summarization: fast
    classification: cheap
    complex_reasoning: smart
    translation: balanced
    chat: fast

  # 条件规则（按顺序匹配，命中即停）
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
# 智能路由（P2）
# ============================================================
smart_routing:
  enabled: false
  strategy: cost_optimized # cost_optimized / quality_first / latency_first / balanced
  constraints:
    max_cost_per_request: 0.05
    max_latency_ms: 3000
    min_quality_score: 0.8

# ============================================================
# Fallback 链
# ============================================================
fallbacks:
  smart: [gpt4o, claude-sonnet, deepseek-chat]
  fast: [deepseek-chat, qwen-local]

# ============================================================
# 预算控制
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
# 用量追踪
# ============================================================
tracking:
  backend: sqlite # memory / sqlite / redis
  sqlite_path: ~/.pai-llm-config/usage.db
  # redis_url: redis://localhost:6379/0

# ============================================================
# 外部名称映射（适配第三方硬编码的模型名）
# ============================================================
mappings:
  "openai/gpt-4": smart
  "gpt-4": smart
  "gpt-4o": gpt4o

# ============================================================
# 多环境覆盖（Profile）
# ============================================================
profiles:
  development:
    providers:
      openai-proxy:
        api_base: https://dev-proxy.com/v1
    defaults:
      temperature: 0.9 # 开发环境更随机

  production:
    providers:
      openai-proxy:
        api_base: https://prod-proxy.com/v1
    defaults:
      temperature: 0.3 # 生产环境更稳定
```

### 1.2 配置优先级（从高到低）

```
环境变量 > .env 文件 > Profile 覆盖（profiles.{name}） > 配置文件主体 > defaults
```

### 1.3 单 Key 与多 Key 兼容

```yaml
# 单 Key 简写 — 向后兼容，零迁移成本
providers:
  anthropic:
    api_key: ${ANTHROPIC_API_KEY}

# 多 Key 完整写法
providers:
  openai-proxy:
    api_keys:
      - key: ${KEY_1}
        priority: 1
      - key: ${KEY_2}
        priority: 2
    key_strategy: priority
```

内部统一转换为 KeyPool，单 Key 等价于只有一个元素的 Key 池。

`key_strategy` 支持两级配置：provider 级设置默认策略，模型级可覆盖。同一 provider 下不同模型可以使用不同策略（例如 GPT-4 用 `priority` 省钱，GPT-3.5 用 `round_robin` 分散负载）。模型级未配置时继承 provider 级策略。

### 1.4 Provider 类型

每个 provider 必须声明 `type` 字段，用于决定使用哪种 SDK 协议：

| type          | 说明                                                  | 对应 SDK                 |
| ------------- | ----------------------------------------------------- | ------------------------ |
| `openai`    | OpenAI-compatible 协议（含代理、DeepSeek、Ollama 等） | `openai`               |
| `anthropic` | Anthropic 原生协议                                    | `anthropic`            |
| `azure`     | Azure OpenAI 协议                                     | `openai`（Azure 模式） |
| `litellm`   | 通过 LiteLLM 统一代理                                 | `litellm`              |

`type` 字段不可省略。如果缺失，加载时抛出 `ConfigValidationError`。

> **设计决策**：不做自动推断。provider 名称是用户自定义的（如 `openai-proxy`、`my-company-gateway`），无法可靠推断协议类型。显式声明消除歧义，也让配置文件自文档化。

### 1.5 最小配置

对于"一个 provider + 一个模型"的简单场景，最小可用配置如下：

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

使用：

```python
from pai_llm_config import LLMConfig

config = LLMConfig()
client = config.create_client("gpt4o")
response = client.chat.completions.create(
    messages=[{"role": "user", "content": "Hello"}]
)
```

未声明的参数（temperature、max_tokens 等）使用 SDK 默认值，不强制要求配置 defaults、aliases、routing 等高级功能。

### 1.6 Profile 覆盖范围

`profiles` 块支持覆盖以下顶层字段：

| 字段          | 可覆盖 | 说明                                  |
| ------------- | ------ | ------------------------------------- |
| `defaults`  | ✅     | 覆盖全局默认参数                      |
| `providers` | ✅     | 覆盖 provider 的 api_base、api_key 等 |
| `models`    | ✅     | 覆盖模型参数（如 temperature）        |
| `aliases`   | ✅     | 不同环境指向不同模型                  |
| `routing`   | ✅     | 不同环境使用不同路由规则              |
| `budgets`   | ✅     | 不同环境设置不同预算                  |
| `tracking`  | ✅     | 不同环境使用不同追踪后端              |
| `fallbacks` | ✅     | 不同环境使用不同 fallback 链          |
| `mappings`  | ✅     | 不同环境使用不同外部名称映射          |

覆盖采用深度合并（deep merge）策略：Profile 配置与主配置递归合并，Profile 配置优先。列表类型字段（如 `api_keys`）整体替换而非追加。

### 1.7 配置文件自动发现

`LLMConfig.load()` 不传路径时，自动从项目根目录查找配置文件，零配置即可使用。

#### 查找策略

1. 确定项目根目录（按优先级）：

   - 环境变量 `LLM_CONFIG_ROOT`（显式指定）
   - `flashboot_core.utils.project_utils.get_root_path()`（如果已安装）
   - 向上查找 `pyproject.toml` / `.git` 等标记文件（内置 fallback）
2. 从项目根目录按顺序查找配置文件（命中即停）：

```
{root}/llm-config.yaml
{root}/llm-config.yml
{root}/config/llm-config.yaml
{root}/config/llm-config.yml
{root}/resources/llm-config.yaml
{root}/resources/llm-config.yml
{root}/.llm-config.yaml              # 隐藏文件风格
```

3. Profile 自动检测（按优先级）：
   - `LLM_CONFIG_PROFILE` 环境变量（推荐）
   - `LLM_CONFIG_ENV` 环境变量（向后兼容）
   - `flashboot_core.env.Environment.get_active_profiles()`（如果已安装）
   - 默认不激活任何 Profile

#### 与 flashboot_core 的集成

flashboot_core 是可选依赖，不强制安装。集成采用运行时检测：

```python
# pai_llm_config 内部实现
def _find_root() -> Path:
    # 1. 显式环境变量
    if root := os.environ.get("LLM_CONFIG_ROOT"):
        return Path(root)

    # 2. flashboot_core（如果可用）
    try:
        from flashboot_core.utils import project_utils
        return Path(project_utils.get_root_path())
    except ImportError:
        pass

    # 3. 内置 fallback — 向上查找标记文件
    return _find_root_by_markers(Path.cwd())
```

这样在 flashboot_core 生态内的项目自动受益于其智能根路径发现（git/svn/markers/structure），独立使用时也能正常工作。

### 1.8 全局单例（零样板代码）

LLM 配置在项目中到处使用，每次都手动 load + 传递 config 对象很繁琐。提供全局单例模块，一行代码直接用：

```python
# ============================================================
# 任意模块中直接使用，无需手动 load
# ============================================================
from pai_llm_config import llm

# L2 — 拿客户端
client = llm.create_client("smart")                  # -> OpenAI(...) 或 Anthropic(...)
client = llm.openai_client("smart")                  # -> OpenAI(...)（类型化）
client = llm.anthropic_client("claude-sonnet")       # -> anthropic.Anthropic(...)

# L1 — 拿参数（可直接传给任何框架）
params = llm.params("gpt4o")                         # -> dict
params = llm.litellm_params("gpt4o")                 # -> dict（LiteLLM 格式）

# 也可一行接入 LangChain / DSPy 等框架：
# from langchain_openai import ChatOpenAI
# chat = ChatOpenAI(**llm.params("smart"))

# 路由
model = llm.route("code_generation")                 # -> ModelConfig

# 配置信息
llm.list_models()
llm.list_aliases()
```

#### 内部机制

```python
# pai_llm_config/llm.py
from pai_llm_config import LLMConfig

_config: LLMConfig | None = None

def _get_config() -> LLMConfig:
    global _config
    if _config is None:
        _config = LLMConfig.load()              # 自动发现，首次访问时加载
    return _config

def client(name: str):
    return _get_config().create_client(name)

def openai_client(name: str):
    return _get_config().create_openai_client(name)

def params(name: str) -> dict:
    return _get_config().to_params(name)

# ... 其他方法同理
```

特性：

- 懒加载 — 首次调用时才加载配置，import 零开销
- 线程安全 — 内部使用 `threading.Lock` 保护初始化
- 可重置 — `llm.reload()` 强制重新加载（配置文件变更后）
- 可覆盖 — `llm.configure(config)` 手动注入 LLMConfig 实例（测试场景）

#### 对比

```python
# ❌ 之前：3 行，需要传递 config 对象
from pai_llm_config import LLMConfig
config = LLMConfig.load("llm-config.yaml", profile="production")
client = config.create_openai_client("smart")

# ✅ 之后：1 行，到处直接用
from pai_llm_config import llm
client = llm.openai_client("smart")
```

---
