# 架构设计

## 1. 架构设计

### 1.1 包结构

```
pai-llm-config/
├── pai_llm_config/
│   ├── __init__.py                # 公开 API：LLMConfig, ModelConfig, llm 单例
│   ├── config.py                  # LLMConfig 主类
│   ├── models.py                  # Pydantic 数据模型
│   ├── loader.py                  # 多源加载 + 合并 + Profile 覆盖
│   ├── resolver.py                # ${VAR} 变量解析
│   │
│   ├── keypool/                   # 多 Key 池管理
│   │   ├── __init__.py
│   │   ├── pool.py                # KeyPool 管理器
│   │   ├── strategies.py          # Key 选择策略
│   │   ├── tracker.py             # 用量追踪（memory / sqlite / redis）
│   │   └── health.py              # Key 健康检查
│   │
│   ├── clients/                   # L2 — SDK 客户端工厂
│   │   ├── __init__.py
│   │   └── factory.py             # ClientFactory 主逻辑（OpenAI / Anthropic / LiteLLM）
│   │
│   ├── routing/                   # 模型路由
│   │   ├── __init__.py
│   │   ├── static.py              # 静态预设路由
│   │   ├── condition.py           # 条件规则路由
│   │   └── smart.py               # 智能路由（P2）
│   │
│   ├── budget.py                  # 预算控制
│   │
│   └── cli.py                     # CLI 工具（P2）
│
├── pyproject.toml
├── tests/
└── examples/
```

### 1.2 核心类图

```
LLMConfig（主入口）
├── Loader（配置加载）
│   ├── YAMLLoader
│   ├── TOMLLoader
│   ├── EnvLoader
│   └── DotenvLoader
│
├── Resolver（变量解析）
│   └── ${VAR} -> 实际值
│
├── ModelRegistry（模型注册表）
│   ├── ModelConfig（模型配置）
│   └── AliasMap（别名映射）
│
├── ProviderRegistry（Provider 注册表）
│   └── ProviderConfig
│       └── KeyPool（Key 池）
│           ├── KeyConfig
│           ├── Strategy（选择策略）
│           └── UsageTracker（用量追踪）
│
├── ClientFactory（L2 — SDK 客户端工厂）
│   ├── OpenAI / OpenAI-compatible  # 含 DeepSeek、Azure 等
│   ├── Anthropic 原生 SDK
│   └── LiteLLM 统一接口
│   （内置：Key 轮换钩子 + 用量自动上报 + 默认参数注入）
│
├── Router（路由引擎）
│   ├── StaticRouter（静态预设）
│   ├── ConditionRouter（条件规则）
│   └── SmartRouter（智能路由，P2）
│
└── BudgetManager（预算管理）
```

### 1.3 Key 池核心逻辑

```python
class KeyPool:
    """管理一个 Provider 的多个 API Key"""

    def __init__(self, keys: list[KeyConfig], strategy: str):
        self.keys = keys
        self.strategy = load_strategy(strategy)
        self.tracker = UsageTracker()

    def get_key(self) -> str:
        """根据策略返回当前最优 Key"""
        available = [k for k in self.keys if self._is_available(k)]
        if not available:
            raise AllKeysExhaustedError("所有 Key 额度已用完")
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

### 1.4 路由策略接口

```python
from typing import Protocol

class RouterStrategy(Protocol):
    def select(self, prompt: str, candidates: list[ModelConfig]) -> ModelConfig: ...

# 内置策略
class CostOptimizedRouter(RouterStrategy):
    """用最便宜的能胜任的模型（内部用轻量分类器判断 prompt 复杂度）"""

class QualityFirstRouter(RouterStrategy):
    """优先质量，成本为约束"""

class LatencyFirstRouter(RouterStrategy):
    """优先速度"""

# 外部集成
class RouteLLMRouter(RouterStrategy):
    """集成 RouteLLM 开源方案"""

class UnifyRouter(RouterStrategy):
    """集成 Unify AI API"""
```

### 1.5 并发安全

LLM 应用通常涉及多线程或异步并发调用，KeyPool 和 UsageTracker 必须保证线程安全。

```python
import threading
from asyncio import Lock as AsyncLock

class KeyPool:
    def __init__(self, keys: list[KeyConfig], strategy: str):
        self.keys = keys
        self.strategy = load_strategy(strategy)
        self.tracker = UsageTracker()
        self._lock = threading.Lock()          # 同步场景
        self._async_lock = AsyncLock()          # 异步场景

    def get_key(self) -> str:
        with self._lock:
            available = [k for k in self.keys if self._is_available(k)]
            if not available:
                raise AllKeysExhaustedError("所有 Key 额度已用完")
            return self.strategy.select(available, self.tracker)

    async def aget_key(self) -> str:
        async with self._async_lock:
            available = [k for k in self.keys if self._is_available(k)]
            if not available:
                raise AllKeysExhaustedError("所有 Key 额度已用完")
            return self.strategy.select(available, self.tracker)
```

UsageTracker 的并发策略取决于后端：

- memory — `threading.Lock` 保护内存数据结构
- sqlite — 依赖 SQLite 内置的写锁（WAL 模式），单连接串行写入
- redis — 使用 Redis 原子操作（INCRBY、HINCRBY），天然线程安全

### 1.6 重试与 Key 故障转移

当 API 调用因 Key 相关错误（429 Rate Limit、401 Unauthorized、403 Forbidden）失败时，自动切换到下一个可用 Key 重试：

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
                    continue                   # 换 Key 重试
                self._report_usage_if_available(response, current_key)
                return response
            except Exception as e:
                self._key_pool.report_error(current_key, e)
                last_error = e

        raise AllKeysExhaustedError("所有 Key 均不可用") from last_error
```

重试策略配置：

```yaml
providers:
  openai-proxy:
    type: openai
    retry:
      max_retries: 3 # 最大重试次数（跨 Key）
      retry_on: [429, 401, 403] # 触发重试的 HTTP 状态码
      backoff: false # Key 轮换场景下不需要退避，直接换 Key
```

非 Key 相关错误（500、网络超时等）不触发 Key 轮换，由上层业务或 SDK 自带重试处理。

### 1.7 日志规范

配置管理库涉及 API Key 和调用信息，日志必须遵循安全规范：

```python
import logging

logger = logging.getLogger("pai_llm_config")

# Key 脱敏 — 只显示前 6 位和后 4 位
def mask_key(key: str) -> str:
    if len(key) <= 12:
        return "***"
    return f"{key[:6]}...{key[-4:]}"

# 日志级别约定：
# DEBUG  — Key 选择决策、参数合并过程（开发调试用）
# INFO   — 客户端创建、Key 轮换事件、配置加载完成
# WARNING — Key 额度接近上限、budget 告警、fallback 触发
# ERROR  — 所有 Key 耗尽、配置加载失败
```

规则：

- 所有日志中的 API Key 必须经过 `mask_key()` 脱敏
- 不在日志中输出请求/响应的完整 body（可能包含用户敏感数据）
- 使用标准 `logging` 模块，不强制日志框架，用户可自行配置 handler

### 1.8 配置语义校验

Pydantic 负责类型校验，但以下语义错误需要在 `LLMConfig.load()` 时额外校验：

| 校验规则                               | 错误类型                   | 示例                                      |
| -------------------------------------- | -------------------------- | ----------------------------------------- |
| 模型引用的 provider 必须存在           | `ProviderNotFoundError`  | `provider: nonexistent`                 |
| 别名指向的模型必须存在                 | `ModelNotFoundError`     | `smart: nonexistent-model`              |
| fallback 链中的模型必须全部存在        | `ModelNotFoundError`     | `fallbacks.smart: [gpt4o, nonexistent]` |
| routing rules 引用的模型/别名必须存在  | `ModelNotFoundError`     | `routing.presets.code: nonexistent`     |
| 别名不能与模型名冲突                   | `AliasConflictError`     | 别名 `gpt4o` 与模型名 `gpt4o` 重复    |
| chat 别名不能指向 embedding 模型       | `ModelTypeMismatchError` | `smart: text-embedding-3`               |
| 环境覆盖中引用的 provider/模型必须存在 | `ConfigValidationError`  | Profile 覆盖引用未定义的 provider             |

校验在配置加载完成后、返回 `LLMConfig` 实例前一次性执行，收集所有错误后统一抛出：

```python
config = LLMConfig.load("llm-config.yaml")
# 如果有语义错误，抛出 ConfigValidationError，包含所有错误列表：
# ConfigValidationError: 3 validation errors:
#   - models.gpt4o: provider 'nonexistent' not found
#   - aliases.smart: model 'nonexistent-model' not found
#   - fallbacks.smart[1]: model 'nonexistent' not found
```

---
