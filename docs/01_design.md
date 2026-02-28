# LLM 统一配置管理库 — 设计背景与需求规格

## 1. 项目背景

### 1.1 问题描述

当前 LLM 应用开发中，配置管理面临以下痛点：

#### 配置与环境管理

| 痛点               | 描述                                                                                    | 解决方案                                                                                               |
| ------------------ | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| 配置碎片化         | 每个框架各有一套配置方式，开发者需要重复处理相同的配置逻辑                              | F01 多源配置加载 + F07 参数适配输出：一份 YAML 配置，`to_params()` 输出各 SDK 所需格式               |
| 环境切换繁琐       | 开发/测试/生产环境的配置切换需要手动处理                                                | F03 多环境支持 + F17 配置继承：profiles 覆盖机制，一键切换                                             |
| 团队配置共享无标准 | 团队内"用哪个模型、什么参数"靠口头约定或 wiki，没有可版本控制、可 review 的标准配置文件 | YAML 配置文件天然可 Git 版本控制，配合 `${VAR}` 变量引用实现密钥与配置分离，团队共享配置结构而非密钥 |

#### SDK 集成

| 痛点                | 描述                                                                                        | 解决方案                                                                                         |
| ------------------- | ------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| SDK 集成胶水代码多  | 拿到配置后还要手动创建 OpenAI/Anthropic 客户端、处理 Key 注入、用量上报，每个项目重复写一遍 | F23 客户端工厂：`config.create_client("smart")` 直接返回带 Key 轮换和用量追踪的 SDK 客户端实例 |
| 框架切换成本高      | 从 OpenAI SDK 切到 LiteLLM，或从 LangChain 切到 DSPy，需要重写客户端创建和调用逻辑          | F07 两层适配：L1 配置参数输出 → L2 客户端工厂，`to_params()` 可直接传给任何框架               |
| Key 轮换与 SDK 脱节 | Key 池管理和 SDK 调用是两套独立逻辑，开发者需要自己在调用前选 Key、调用后上报用量           | L2 客户端工厂内置 Key 轮换钩子，每次调用自动选 Key、自动上报用量，对业务代码完全透明             |

#### 密钥与安全

| 痛点            | 描述                                                                   | 解决方案                                                                                    |
| --------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| 密钥管理混乱    | API Key 散落在代码、环境变量、配置文件中，缺乏统一管理                 | F04 密钥安全：`${ENV_VAR}` 引用 + .env 加载，密钥不落配置文件；P2 阶段集成 Vault / AWS SM |
| 多 Key 轮换缺失 | 中转 API 场景下，一个模型对应多个 Key（按额度/频率轮换），没有现成方案 | F08-F11 多 Key 池：KeyPool 自动管理多 Key 的选择、轮换、健康检查，对业务代码完全透明        |

#### 模型管理

| 痛点                | 描述                                                                                                                   | 解决方案                                                                                                                          |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| 多模型协调困难      | 一个系统中同时使用多个模型（按能力/价格/场景分工），缺乏统一的模型注册和路由机制                                       | F06 模型别名 + F12/F13 路由：语义别名（smart/fast/cheap）+ 静态预设/条件规则路由                                                  |
| 模型废弃/迁移成本高 | Provider 频繁废弃旧模型（gpt-4-turbo → gpt-4o、claude-3 → claude-4），配置散落在代码各处时，每次迁移都是全局搜索替换 | F06 模型别名：业务代码只引用别名（smart），模型迁移只需改 YAML 中别名的映射目标，零代码改动                                       |
| Provider 锁定       | 业务代码直接耦合某个 Provider 的 SDK/参数格式，想从 OpenAI 切到 DeepSeek 或 Anthropic 需要改代码                       | F02 多 Provider 统一抽象 + F07 框架适配输出：统一配置格式屏蔽 Provider 差异，切换 Provider 只改配置                               |
| 模型能力信息分散    | 选模型时需要查各家文档确认 context window、是否支持 vision/function calling 等，没有统一的能力注册表                   | models 配置中的 capabilities / max_context / cost / latency_tier 字段构成统一的模型能力注册表，条件路由可直接基于这些元数据选模型 |

#### 成本与可观测性

| 痛点         | 描述                                                                                      | 解决方案                                                                                   |
| ------------ | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| 成本不可观测 | 多模型并行使用时，不知道钱花在哪、哪个任务最烧钱、哪个 Key 快到限额了，出了账单才发现超支 | F10 Key 用量追踪 + F15 预算控制：按 Key/模型/全局维度追踪用量，支持日/月限额和事件回调预警 |

### 1.2 市场现状

| 项目                   | 定位         | 不足                               |
| ---------------------- | ------------ | ---------------------------------- |
| Dynaconf               | 通用配置管理 | 非 LLM 领域，无模型路由/Key 池概念 |
| LiteLLM                | LLM 调用网关 | 偏运行时，配置管理不够优雅         |
| LiteLLM Router         | 负载均衡     | 基于规则，缺乏智能路由             |
| RouteLLM (LMSys)       | 智能路由     | 只做路由，不管配置                 |
| Portkey AI             | API 网关     | 闭源 SaaS，不可私有化              |
| Unify AI / Not Diamond | 智能路由     | 闭源 API 服务                      |

### 1.3 项目定位

pai-llm-config 是一个 **LLM 领域原生的配置管理库**，核心理念：

> 一份 YAML 描述所有模型的能力和成本，业务代码只说"我要做什么"，库来决定"用哪个模型、用哪个 Key"。

### 1.4 包关系设计

pai-llm-config 作为独立包发布，同时通过 pai-llm 提供透传导入，用户无需感知底层拆分。

```
pai-llm（主包，用户感知的入口）
├── pai_llm.config          →  透传自 pai_llm_config（re-export）
├── pai_llm.conversation    →  对话历史管理（已有）
├── pai_llm.prompt          →  Prompt Hub（规划中）
└── ...

pai-llm-config（独立包，独立仓库，独立发版）
└── pai_llm_config/
    ├── __init__.py          →  LLMConfig, ModelConfig, ...
    ├── config.py
    ├── models.py
    └── ...
```

#### 安装方式

```bash
# 方式1：只装 config（轻量，不依赖 pai-llm 的其他功能）
pip install pai-llm-config

# 方式2：装 pai-llm，自动包含 config（推荐，一站式）
pip install pai-llm[config]
# 或者全家桶
pip install pai-llm[all]
```

#### 导入方式

```python
# 方式1：直接从独立包导入（明确、无歧义）
from pai_llm_config import LLMConfig

# 方式2：从 pai-llm 透传导入（对用户更友好，不用记多个包名）
from pai_llm_config import LLMConfig

# 两种方式完全等价，返回同一个类
```

#### pai-llm 侧的实现

```python
# pai_llm/config/__init__.py — 透传导入
try:
    from pai_llm_config import *           # noqa: F401,F403
    from pai_llm_config import LLMConfig   # 显式导出，保证 IDE 补全
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

#### 设计原则

- pai-llm-config 零依赖 pai-llm，可以完全独立使用
- pai-llm 通过 optional dependency + re-export 提供透传
- 用户只需记住 `from pai_llm_config import LLMConfig`，不用关心底层是哪个包
- 未来 pai-llm 的其他番外库（如 pai-llm-prompt、pai-llm-agent）也可以用同样的模式

### 1.5 差异化卖点

1. **LLM 领域原生** — 配置格式为 LLM 场景设计，开箱即用
2. **框架桥接** — 一份配置，输出为各 SDK 所需参数格式（OpenAI / Anthropic / LiteLLM），也可直接传给 LangChain、DSPy 等框架
3. **模型别名 + 路由** — 业务代码只关心语义（smart/fast），不关心具体模型
4. **多 Key 池** — 自动轮换、额度追踪、健康检查
5. **渐进式集成** — L1 纯配置零侵入，L2 按需接管客户端创建；`to_params()` 可直接传给 LangChain、DSPy 等任何框架

### 1.6 兼容性分析

#### Provider 覆盖

| Provider 类型     | 代表                                                                      | L2 支持方式                                                              | 覆盖度 |
| ----------------- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------ | ------ |
| OpenAI-compatible | OpenAI、Azure、DeepSeek、Moonshot、智谱、零一万物、Ollama、vLLM、各种中转 | OpenAI 客户端直接支持                                                    | 强     |
| Anthropic         | Claude 系列                                                               | Anthropic 原生客户端                                                     | 强     |
| Google            | Gemini 系列                                                               | OpenAI-compatible 模式（`type: openai` + Google 官方 OpenAI 兼容端点） | 强     |
| AWS Bedrock       | Claude/Llama/Mistral via AWS                                              | LiteLLM 客户端兜底                                                       | 中     |
| Mistral           | Mistral 官方 API                                                          | OpenAI-compatible 模式可用                                               | 中     |
| 其他              | Cohere、AI21 等                                                           | LiteLLM 客户端兜底（支持 100+ Provider）                                 | 中     |

策略：L2 原生客户端覆盖 OpenAI-compatible + Anthropic（~80% 场景），Google Gemini 通过官方 OpenAI 兼容端点同样归入 OpenAI-compatible，LiteLLM 客户端兜底其余所有 Provider。

#### 框架覆盖

| 框架          | 支持层级            | 优先级 |
| ------------- | ------------------- | ------ |
| OpenAI SDK    | L2 客户端工厂       | P0     |
| Anthropic SDK | L2 客户端工厂       | P0     |
| LiteLLM       | L1 参数 + L2 客户端 | P0     |

#### API 模式覆盖

| API 模式              | 支持情况                                                       | 优先级 |
| --------------------- | -------------------------------------------------------------- | ------ |
| Chat Completions      | L2 包装 `chat.completions.create` / `messages.create`      | P0     |
| Streaming             | L2 包装 stream=True，用量在流结束后上报                        | P0     |
| Async                 | `create_async_client()`                                      | P0     |
| Embeddings            | models 配置 `type: embedding`，L2 包装 `embeddings.create` | P1     |
| Image Generation      | 不覆盖                                                         | —     |
| Audio (TTS/STT)       | 不覆盖                                                         | —     |
| Tool/Function Calling | capabilities 元数据，无需特殊处理                              | —     |

#### SDK API 形状差异处理

不同 Provider 的 SDK API 形状不同，L2 客户端工厂按 Provider 类型分别包装：

```python
# OpenAI-compatible — 包装 chat.completions.create
client = config.create_client("gpt4o")
response = client.chat.completions.create(messages=[...])
# 返回原生 OpenAI 客户端，API 形状不变

# Anthropic — 包装 messages.create
client = config.create_client("claude-sonnet")
response = client.messages.create(max_tokens=1024, messages=[...])
# 返回原生 Anthropic 客户端，API 形状不变
# 内部包装 messages.create 注入 Key 轮换 + 用量上报

# LiteLLM — 统一接口，屏蔽所有差异
client = config.litellm_client("smart")
response = client.completion(model="smart", messages=[...])
# 无论底层是 OpenAI/Anthropic/Gemini，调用方式统一
```

设计原则：L2 不改变 SDK 的 API 形状，只在内部注入 Key 轮换和用量追踪。用户拿到的客户端和直接用原生 SDK 一样，IDE 补全、类型提示完全保留。如果需要统一 API 形状，用 LiteLLM 客户端。

## 2. 需求规格

### 2.1 P0 — 核心功能（v0.1 ~ v0.2）

| 编号 | 需求                 | 描述                                                                                               |
| ---- | -------------------- | -------------------------------------------------------------------------------------------------- |
| F01  | 多源配置加载         | 支持 .env、环境变量、YAML/TOML 文件，优先级可控                                                    |
| F02  | 多 Provider 统一抽象 | OpenAI、Anthropic、Azure、本地模型（Ollama/vLLM）、国内中转，统一配置格式                          |
| F03  | 多环境支持           | dev / staging / prod 一键切换                                                                      |
| F04  | 密钥安全             | 支持 `${ENV_VAR}` 引用、.env 加载，密钥不落配置文件                                              |
| F05  | 类型校验             | 配置项有明确类型，加载时校验，错误提前暴露                                                         |
| F06  | 模型别名             | 定义 smart、fast、cheap 等语义别名映射到具体模型                                                   |
| F07  | 参数适配输出         | 两层适配：L1 配置参数 dict → L2 SDK 客户端工厂（OpenAI / Anthropic / LiteLLM）                    |
| F23  | 客户端工厂           | `create_client()` 直接返回带 Key 轮换和用量追踪的 SDK 客户端实例（OpenAI / Anthropic / LiteLLM） |
| F24  | Streaming 支持       | L2 客户端包装 stream=True 模式，流结束后自动上报用量                                               |

### 2.2 P1 — 增强功能（v0.3 ~ v0.5）

| 编号 | 需求               | 描述                                                                              |
| ---- | ------------------ | --------------------------------------------------------------------------------- |
| F08  | 多 Key 池          | 一个 Provider 配置多个 API Key，按策略自动选择                                    |
| F09  | Key 选择策略       | 支持 priority / round_robin / least_used / random                                 |
| F10  | Key 用量追踪       | 追踪每个 Key 的用量（token/费用/请求数）                                          |
| F11  | Key 健康检查       | 连续报错自动标记不可用，定期恢复探测                                              |
| F12  | 静态任务路由       | 按预设规则将任务类型映射到模型                                                    |
| F13  | 条件路由           | 按 token 数、capabilities 等条件动态选择模型                                      |
| F14  | Fallback 链        | 主模型不可用时按链路自动降级                                                      |
| F15  | 预算控制           | 按模型/全局设置日/月费用上限                                                      |
| F16  | 默认参数           | temperature、max_tokens 等可按模型/全局设置默认值                                 |
| F17  | 配置继承           | 子环境继承父环境配置，只覆盖差异项                                                |
| F25  | Embedding 模型支持 | models 配置支持 `type: embedding`，L2 包装 `embeddings.create`，适配 RAG 场景 |

### 2.3 P2 — 高级功能（v0.6 ~ v0.7）

| 编号 | 需求             | 描述                                                                   |
| ---- | ---------------- | ---------------------------------------------------------------------- |
| F18  | 智能路由         | 根据 prompt 复杂度自动选择最优模型（集成 RouteLLM 或自训练分类器）     |
| F19  | CLI 工具         | `pai-llm-config init` 生成模板、`pai-llm-config validate` 校验配置 |
| F20  | 密钥管理服务集成 | AWS Secrets Manager / Azure Key Vault / HashiCorp Vault                |
| F21  | 热重载           | 运行时配置变更无需重启                                                 |
| F22  | 分布式用量追踪   | Redis 后端，支持多进程/多实例共享用量数据                              |
