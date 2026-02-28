"""Unit tests for pai_llm_config.models — Pydantic model validation."""

import pytest
from pydantic import ValidationError

from pai_llm_config.models import (
    KeyConfig,
    DefaultsConfig,
    ProviderConfig,
    ModelConfig,
    AliasConfig,
    LLMConfigSchema,
    RoutingPreset,
    RoutingConfig,
    RoutingRule,
    RoutingCondition,
    FallbackConfig,
    BudgetConfig,
    BudgetsConfig,
    TrackingConfig,
    SmartRoutingConfig,
    ProfileOverride,
)


# ============================================================
# KeyConfig
# ============================================================


class TestKeyConfig:
    def test_valid_key(self):
        k = KeyConfig(key="sk-test")
        assert k.key == "sk-test"
        assert k.alias is None
        assert k.priority is None

    def test_empty_key_invalid(self):
        with pytest.raises(ValidationError):
            KeyConfig(key="")

    def test_with_alias_and_priority(self):
        k = KeyConfig(key="sk-1", alias="primary", priority=1)
        assert k.alias == "primary"
        assert k.priority == 1

    def test_invalid_priority_zero(self):
        with pytest.raises(ValidationError):
            KeyConfig(key="sk-1", priority=0)

    def test_invalid_priority_negative(self):
        with pytest.raises(ValidationError):
            KeyConfig(key="sk-1", priority=-1)

    def test_daily_limit_positive(self):
        k = KeyConfig(key="sk-1", daily_limit_usd=5.0)
        assert k.daily_limit_usd == 5.0

    def test_daily_limit_zero_invalid(self):
        with pytest.raises(ValidationError):
            KeyConfig(key="sk-1", daily_limit_usd=0.0)

    def test_daily_limit_negative_invalid(self):
        with pytest.raises(ValidationError):
            KeyConfig(key="sk-1", daily_limit_usd=-1.0)

    def test_rpm_tpm_limits(self):
        k = KeyConfig(key="sk-1", rpm_limit=100, tpm_limit=10000)
        assert k.rpm_limit == 100
        assert k.tpm_limit == 10000

    def test_rpm_zero_invalid(self):
        with pytest.raises(ValidationError):
            KeyConfig(key="sk-1", rpm_limit=0)


# ============================================================
# DefaultsConfig
# ============================================================


class TestDefaultsConfig:
    def test_all_defaults_none(self):
        d = DefaultsConfig()
        assert d.temperature is None
        assert d.max_tokens is None
        assert d.top_p is None

    def test_temperature_valid_range(self):
        assert DefaultsConfig(temperature=0.0).temperature == 0.0
        assert DefaultsConfig(temperature=1.0).temperature == 1.0
        assert DefaultsConfig(temperature=2.0).temperature == 2.0

    def test_temperature_below_zero_invalid(self):
        with pytest.raises(ValidationError):
            DefaultsConfig(temperature=-0.1)

    def test_temperature_above_two_invalid(self):
        with pytest.raises(ValidationError):
            DefaultsConfig(temperature=2.1)

    def test_top_p_valid_range(self):
        assert DefaultsConfig(top_p=0.0).top_p == 0.0
        assert DefaultsConfig(top_p=0.5).top_p == 0.5
        assert DefaultsConfig(top_p=1.0).top_p == 1.0

    def test_top_p_above_one_invalid(self):
        with pytest.raises(ValidationError):
            DefaultsConfig(top_p=1.1)

    def test_top_p_below_zero_invalid(self):
        with pytest.raises(ValidationError):
            DefaultsConfig(top_p=-0.1)

    def test_max_tokens_positive(self):
        assert DefaultsConfig(max_tokens=100).max_tokens == 100

    def test_max_tokens_zero_invalid(self):
        with pytest.raises(ValidationError):
            DefaultsConfig(max_tokens=0)

    def test_max_tokens_negative_invalid(self):
        with pytest.raises(ValidationError):
            DefaultsConfig(max_tokens=-1)

    def test_alias_temp(self):
        """'temp' should be accepted as alias for 'temperature'."""
        d = DefaultsConfig.model_validate({"temp": 0.5})
        assert d.temperature == 0.5

    def test_alias_max_tokens_hyphen(self):
        """'max-tokens' should be accepted."""
        d = DefaultsConfig.model_validate({"max-tokens": 1024})
        assert d.max_tokens == 1024

    def test_alias_max_completion_tokens(self):
        d = DefaultsConfig.model_validate({"max_completion_tokens": 2048})
        assert d.max_tokens == 2048

    def test_stop_string(self):
        d = DefaultsConfig(stop="END")
        assert d.stop == "END"

    def test_stop_list(self):
        d = DefaultsConfig(stop=["END", "\n\n"])
        assert d.stop == ["END", "\n\n"]

    def test_response_format_dict(self):
        d = DefaultsConfig(response_format={"type": "json_object"})
        assert d.response_format == {"type": "json_object"}

    def test_seed_integer(self):
        d = DefaultsConfig(seed=42)
        assert d.seed == 42


# ============================================================
# ProviderConfig
# ============================================================


class TestProviderConfig:
    def test_minimal_provider(self):
        p = ProviderConfig(type="openai")
        assert p.type == "openai"
        assert p.api_key is None

    def test_all_provider_types(self):
        for t in ("openai", "anthropic", "azure", "litellm"):
            p = ProviderConfig(type=t)
            assert p.type == t

    def test_invalid_provider_type(self):
        with pytest.raises(ValidationError):
            ProviderConfig(type="invalid")

    def test_api_key_alias_key(self):
        p = ProviderConfig.model_validate({"type": "openai", "key": "sk-test"})
        assert p.api_key == "sk-test"

    def test_api_key_alias_apikey(self):
        p = ProviderConfig.model_validate({"type": "openai", "apikey": "sk-test"})
        assert p.api_key == "sk-test"

    def test_api_key_alias_api_hyphen_key(self):
        p = ProviderConfig.model_validate({"type": "openai", "api-key": "sk-test"})
        assert p.api_key == "sk-test"

    def test_api_base_alias_base_url(self):
        p = ProviderConfig.model_validate(
            {"type": "openai", "base_url": "https://api.example.com"}
        )
        assert str(p.api_base).rstrip("/") == "https://api.example.com"

    def test_api_base_alias_endpoint(self):
        p = ProviderConfig.model_validate(
            {"type": "openai", "endpoint": "https://api.example.com"}
        )
        assert p.api_base is not None

    def test_api_base_alias_base_hyphen_url(self):
        p = ProviderConfig.model_validate(
            {"type": "openai", "base-url": "https://api.example.com"}
        )
        assert p.api_base is not None

    def test_api_version_alias(self):
        p = ProviderConfig.model_validate(
            {"type": "azure", "api-version": "2024-02-01"}
        )
        assert p.api_version == "2024-02-01"

    def test_key_strategy_default(self):
        p = ProviderConfig(type="openai")
        assert p.key_strategy == "priority"

    def test_key_strategy_all_valid(self):
        for s in ("priority", "round_robin", "least_used", "random"):
            p = ProviderConfig(type="openai", key_strategy=s)
            assert p.key_strategy == s

    def test_key_strategy_invalid(self):
        with pytest.raises(ValidationError):
            ProviderConfig(type="openai", key_strategy="invalid")

    def test_api_keys_list(self):
        p = ProviderConfig(
            type="openai",
            api_keys=[
                KeyConfig(key="sk-1", alias="primary"),
                KeyConfig(key="sk-2", alias="secondary"),
            ],
        )
        assert len(p.api_keys) == 2

    def test_organization_field(self):
        p = ProviderConfig(type="openai", organization="org-123")
        assert p.organization == "org-123"


# ============================================================
# ModelConfig
# ============================================================


class TestModelConfig:
    def test_minimal_model(self):
        m = ModelConfig(provider="openai", model="gpt-4o")
        assert m.provider == "openai"
        assert m.model == "gpt-4o"
        assert m.type == "chat"

    def test_empty_provider_invalid(self):
        with pytest.raises(ValidationError):
            ModelConfig(provider="", model="gpt-4o")

    def test_empty_model_invalid(self):
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="")

    def test_embedding_type(self):
        m = ModelConfig(provider="openai", model="text-embedding-3", type="embedding")
        assert m.type == "embedding"

    def test_invalid_type(self):
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4o", type="invalid")

    def test_cost_positive_float(self):
        m = ModelConfig(
            provider="openai",
            model="gpt-4o",
            cost_per_1k_input=0.005,
            cost_per_1k_output=0.015,
        )
        assert m.cost_per_1k_input == 0.005
        assert m.cost_per_1k_output == 0.015

    def test_cost_zero_invalid(self):
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4o", cost_per_1k_input=0.0)

    def test_cost_negative_invalid(self):
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4o", cost_per_1k_input=-1.0)

    def test_max_context_positive(self):
        m = ModelConfig(provider="openai", model="gpt-4o", max_context=128000)
        assert m.max_context == 128000

    def test_max_context_zero_invalid(self):
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4o", max_context=0)

    def test_capabilities_list(self):
        m = ModelConfig(
            provider="openai",
            model="gpt-4o",
            capabilities=["reasoning", "code", "vision"],
        )
        assert m.capabilities == ["reasoning", "code", "vision"]

    def test_capabilities_default_empty(self):
        m = ModelConfig(provider="openai", model="gpt-4o")
        assert m.capabilities == []

    def test_latency_tier_values(self):
        for tier in ("low", "medium", "high"):
            m = ModelConfig(provider="openai", model="gpt-4o", latency_tier=tier)
            assert m.latency_tier == tier

    def test_latency_tier_default(self):
        m = ModelConfig(provider="openai", model="gpt-4o")
        assert m.latency_tier == "medium"

    def test_latency_tier_invalid(self):
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4o", latency_tier="ultra")

    def test_dimensions_for_embedding(self):
        m = ModelConfig(
            provider="openai",
            model="text-embedding-3",
            type="embedding",
            dimensions=1536,
        )
        assert m.dimensions == 1536

    def test_dimensions_zero_invalid(self):
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4o", dimensions=0)

    def test_key_strategy_override(self):
        m = ModelConfig(
            provider="openai", model="gpt-4o", key_strategy="round_robin"
        )
        assert m.key_strategy == "round_robin"

    def test_protocol_field(self):
        m = ModelConfig(provider="openai", model="gpt-4o", protocol="openai-v1")
        assert m.protocol == "openai-v1"

    def test_protocol_alias(self):
        m = ModelConfig.model_validate(
            {"provider": "openai", "model": "gpt-4o", "api_protocol": "anthropic-v1"}
        )
        assert m.protocol == "anthropic-v1"

    def test_temperature_range(self):
        m = ModelConfig(provider="openai", model="gpt-4o", temperature=0.0)
        assert m.temperature == 0.0
        m = ModelConfig(provider="openai", model="gpt-4o", temperature=2.0)
        assert m.temperature == 2.0

    def test_temperature_out_of_range(self):
        with pytest.raises(ValidationError):
            ModelConfig(provider="openai", model="gpt-4o", temperature=2.5)

    def test_max_tokens_alias_hyphen(self):
        m = ModelConfig.model_validate(
            {"provider": "openai", "model": "gpt-4o", "max-tokens": 1024}
        )
        assert m.max_tokens == 1024

    def test_response_format(self):
        m = ModelConfig(
            provider="openai",
            model="gpt-4o",
            response_format={"type": "json_object"},
        )
        assert m.response_format == {"type": "json_object"}

    def test_seed(self):
        m = ModelConfig(provider="openai", model="gpt-4o", seed=42)
        assert m.seed == 42


# ============================================================
# AliasConfig
# ============================================================


class TestAliasConfig:
    def test_valid_alias(self):
        a = AliasConfig(root="gpt4o")
        assert a.root == "gpt4o"

    def test_empty_alias_invalid(self):
        with pytest.raises(ValidationError):
            AliasConfig(root="")


# ============================================================
# Routing models
# ============================================================


class TestRoutingModels:
    def test_routing_preset(self):
        p = RoutingPreset(root="smart")
        assert p.root == "smart"

    def test_routing_preset_empty_invalid(self):
        with pytest.raises(ValidationError):
            RoutingPreset(root="")

    def test_routing_config_defaults(self):
        r = RoutingConfig()
        assert r.presets == {}
        assert r.rules == []

    def test_routing_rule_with_condition(self):
        rule = RoutingRule(
            when=RoutingCondition(max_tokens_gt=1000, capabilities=["code"]),
            use="gpt4o",
        )
        assert rule.when.max_tokens_gt == 1000
        assert rule.use == "gpt4o"

    def test_routing_rule_default_only(self):
        rule = RoutingRule(default="cheap")
        assert rule.default == "cheap"


# ============================================================
# Fallback, Budget, Tracking
# ============================================================


class TestFallbackConfig:
    def test_valid_fallback(self):
        f = FallbackConfig(root=["gpt4o", "claude", "cheap"])
        assert f.root == ["gpt4o", "claude", "cheap"]

    def test_empty_model_in_fallback_invalid(self):
        with pytest.raises(ValidationError):
            FallbackConfig(root=["gpt4o", "", "cheap"])


class TestBudgetConfig:
    def test_defaults(self):
        b = BudgetConfig()
        assert b.daily_limit_usd is None
        assert b.monthly_limit_usd is None

    def test_positive_limits(self):
        b = BudgetConfig(daily_limit_usd=10.0, monthly_limit_usd=300.0)
        assert b.daily_limit_usd == 10.0
        assert b.monthly_limit_usd == 300.0

    def test_zero_limit_invalid(self):
        with pytest.raises(ValidationError):
            BudgetConfig(daily_limit_usd=0.0)


class TestBudgetsConfig:
    def test_global_alias(self):
        """'global' maps to global_ field via alias."""
        b = BudgetsConfig.model_validate(
            {"global": {"daily_limit_usd": 50.0}}
        )
        assert b.global_.daily_limit_usd == 50.0


class TestTrackingConfig:
    def test_defaults(self):
        t = TrackingConfig()
        assert t.backend == "sqlite"

    def test_all_backends(self):
        for backend in ("memory", "sqlite", "redis"):
            t = TrackingConfig(backend=backend)
            assert t.backend == backend


class TestSmartRoutingConfig:
    def test_defaults(self):
        s = SmartRoutingConfig()
        assert s.enabled is False
        assert s.strategy == "cost_optimized"

    def test_all_strategies(self):
        for s in ("cost_optimized", "quality_first", "latency_first", "balanced"):
            cfg = SmartRoutingConfig(strategy=s)
            assert cfg.strategy == s


# ============================================================
# LLMConfigSchema
# ============================================================


class TestLLMConfigSchema:
    def test_minimal_schema(self):
        s = LLMConfigSchema()
        assert s.version == "1"
        assert s.providers == {}
        assert s.models == {}

    def test_full_schema(self):
        s = LLMConfigSchema.model_validate(
            {
                "version": "1",
                "defaults": {"temperature": 0.7, "max_tokens": 4096},
                "providers": {"openai": {"type": "openai", "api_key": "sk-test"}},
                "models": {"gpt4o": {"provider": "openai", "model": "gpt-4o"}},
                "aliases": {"smart": "gpt4o"},
                "routing": {"presets": {"code": "smart"}},
                "mappings": {"openai/gpt-4o": "gpt4o"},
            }
        )
        assert s.defaults.temperature == 0.7
        assert "openai" in s.providers
        assert "gpt4o" in s.models
        assert "smart" in s.aliases
        assert "code" in s.routing.presets
        assert s.mappings["openai/gpt-4o"] == "gpt4o"

    def test_populate_by_name(self):
        """ConfigDict(populate_by_name=True) allows using field names directly."""
        s = LLMConfigSchema.model_validate({"version": "1"})
        assert s.version == "1"
