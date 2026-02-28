"""Unit tests for pai_llm_config routing -- route() presets and route_by()."""

import pytest

from pai_llm_config.config import LLMConfig, ModelNotFoundError


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def config_with_routing():
    return LLMConfig(
        {
            "version": "1",
            "providers": {
                "openai": {"type": "openai", "api_key": "sk-test"},
                "anthropic": {"type": "anthropic", "api_key": "ant-test"},
            },
            "models": {
                "gpt4o": {"provider": "openai", "model": "gpt-4o"},
                "claude": {"provider": "anthropic", "model": "claude-sonnet"},
            },
            "aliases": {"smart": "gpt4o"},
            "routing": {
                "presets": {
                    "code_gen": "smart",
                    "summarization": "claude",
                },
            },
        }
    )


@pytest.fixture
def config_no_routing():
    return LLMConfig(
        {
            "version": "1",
            "providers": {"p1": {"type": "openai", "api_key": "sk-test"}},
            "models": {"m1": {"provider": "p1", "model": "m1"}},
        }
    )


# ============================================================
# TestRoutePresets
# ============================================================


class TestRoutePresets:
    def test_returns_model_for_known_task(self, config_with_routing):
        model = config_with_routing.route("code_gen")
        assert model.model == "gpt-4o"

    def test_resolves_through_alias(self, config_with_routing):
        """code_gen -> alias 'smart' -> model 'gpt4o' -> gpt-4o"""
        model = config_with_routing.route("code_gen")
        assert model.provider == "openai"

    def test_direct_model_reference(self, config_with_routing):
        model = config_with_routing.route("summarization")
        assert model.model == "claude-sonnet"

    def test_unknown_task_raises(self, config_with_routing):
        with pytest.raises(ModelNotFoundError, match="No routing preset found"):
            config_with_routing.route("unknown_task")

    def test_no_presets_raises(self, config_no_routing):
        with pytest.raises(ModelNotFoundError):
            config_no_routing.route("anything")


# ============================================================
# TestRouteBy
# ============================================================


class TestRouteBy:
    def test_raises_not_implemented(self, config_with_routing):
        with pytest.raises(NotImplementedError):
            config_with_routing.route_by(max_tokens=100)
