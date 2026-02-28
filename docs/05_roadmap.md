# LLM 统一配置管理库

## 文档索引

| 文档 | 内容 |
|------|------|
| [01_design.md](01_design.md) | 项目背景、问题描述、市场现状、需求规格 |
| [02_config-spec.md](02_config-spec.md) | YAML 配置文件完整规范（Provider / Model / Alias / Profile） |
| [03_api-reference.md](03_api-reference.md) | Python API 设计（LLMConfig / 路由 / Key 池 / 参数适配） |
| [04_architecture.md](04_architecture.md) | 架构设计、类图、并发安全、Key 池逻辑、语义校验 |
| [05_roadmap.md](05_roadmap.md) | 技术选型 + 版本路线图（本文件） |
| [06_examples.md](06_examples.md) | 使用示例（基础、多模型、DSPy、LangChain、LiteLLM、Gemini） |
| [07_mapping_guide.md](07_mapping_guide.md) | 模型映射与兼容性指南（Mappings 机制、Provider 协议边界） |

---

## 1. 技术选型

| 组件       | 选型                   | 理由                                 |
| ---------- | ---------------------- | ------------------------------------ |
| 配置模型   | Pydantic v2            | 类型校验、序列化、IDE 补全、生态成熟 |
| 文件解析   | PyYAML + tomli         | YAML/TOML 双支持，覆盖主流格式       |
| 环境变量   | python-dotenv          | 轻量标准，社区广泛使用               |
| 变量替换   | 自实现 `${VAR}` 解析 | 简单，不引入额外依赖                 |
| 用量存储   | SQLite（默认）         | 零部署，单机持久化                   |
| 分布式存储 | Redis（可选）          | 多进程/多实例共享                    |
| 框架适配   | 插件模式 + extras      | 按需安装，不强制依赖任何框架         |
| CLI        | click / typer          | 快速构建命令行工具                   |

### 依赖策略

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
openai = ["openai>=1.0"]       # L2 OpenAI / OpenAI-compatible 客户端
anthropic = ["anthropic>=0.30"] # L2 Anthropic 客户端
litellm = ["litellm>=1.0"]     # L2 LiteLLM 统一客户端
redis = ["redis>=5.0"]
vault = ["hvac>=2.0"]           # HashiCorp Vault
aws = ["boto3>=1.34"]           # AWS Secrets Manager
all = ["pai-llm-config[openai,anthropic,litellm,redis,vault,aws]"]
```

---

## 2. 实现路线图

### v0.1 — 能用（核心配置）

- [x] Pydantic 数据模型定义（Provider / Model / Alias）
- [x] YAML 配置文件加载
- [x] `${VAR}` 环境变量解析
- [x] .env 文件加载
- [x] `config.get()` 按名称/别名获取模型配置
- [x] 多环境支持（profiles 覆盖）
- [x] 全局单例 `llm`（懒加载、线程安全、可重置）
- [x] 外部名称映射（mappings）
- [x] 配置文件自动发现（llm-config.yaml/yml，含子目录）
- [x] flashboot_core 集成（项目根路径、Profile 检测）
- [x] 语义校验（provider 引用、别名冲突、类型检查）
- [x] 单元测试（194 tests）

### v0.2 — 好用（参数适配 + 静态路由）

- [x] L1 配置参数输出（to_params / to_litellm_params）
- [x] 默认参数合并逻辑（defaults -> model 级覆盖，含 top_p/stop/seed/response_format）
- [x] L2 客户端工厂 — OpenAI / OpenAI-compatible（create_client / create_async_client）
- [x] L2 客户端工厂 — Anthropic（create_anthropic_client / create_async_anthropic_client）
- [x] L2 客户端工厂 — LiteLLM 统一客户端（create_litellm_client）
- [x] L2 Streaming 支持（stream=True，流结束后自动上报用量）
- [x] 静态任务路由（routing.presets）

### v0.3 — 多 Key 池

- [x] KeyPool 管理器
- [x] priority / round_robin / least_used / random 策略
- [x] 内存用量追踪
- [x] Key 健康检查（错误计数 + 自动标记不可用）
- [x] 单 Key / 多 Key 配置兼容
- [x] L2 客户端工厂集成 Key 轮换钩子（调用前自动选 Key、调用后自动上报用量）
- [ ] Embedding 模型支持（type: embedding，L2 包装 embeddings.create）

### v0.4 — 持久化 + 预算

- [ ] SQLite 用量持久化
- [ ] 预算控制（日/月限额）
- [ ] 事件回调（on_key_exhausted / on_budget_warning）

### v0.5 — 条件路由 + Fallback

- [ ] 条件规则路由（routing.rules）
- [ ] Fallback 链
- [ ] route_by() 接口

### v0.6 — 智能路由

- [ ] RouterStrategy 插件接口
- [ ] 集成 RouteLLM
- [ ] cost_optimized / quality_first / latency_first 策略
- [ ] smart_route() 接口

### v0.7 — 完善

- [ ] CLI 工具（init / validate / status）
- [ ] TOML 配置支持
- [ ] Redis 用量追踪后端
- [ ] 密钥管理服务集成（Vault / AWS SM）
- [ ] 热重载
- [ ] 完整文档 + PyPI 发布

### v0.8 — 生态集成 (LiteLLM Deep Binding)

- [ ] **LiteLLM 配置镜像 (Config Mirroring)**：支持将 `LLMConfig` 导出为 LiteLLM Proxy `config.yaml` 格式。
- [ ] **原生集成工厂 (Native Factory)**：实现 `ModelConfig.to_litellm_params()` 提供给 `litellm.completion` 的全量参数载荷。
- [ ] **治理监测回调 (Governance Callbacks)**：内置 LiteLLM 观测回调，将成本和用量实时泵回 `pai-llm-config` 并触发预警。
- [ ] **统一凭据注入 (Unified Credential Injector)**：打通安全 Provider 密钥向 LiteLLM 运行时上下文的无缝注入。
- [ ] **零配置增强入口 (Zero-config Bridge)**：提供 `pai_llm_config.integrations.litellm` 模块，直接导入即可使用带映射、别名和治理钩子自动加持的 `completion` 函数。

