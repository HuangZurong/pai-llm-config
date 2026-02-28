"""Unit tests for pai_llm_config to_params / to_litellm_params / to_dspy_params output."""

import pytest

from pai_llm_config.config import LLMConfig


@pytest.fixture
def config():
    return LLMConfig(
        {
            "version": "1",
            "defaults": {"temperature": 0.7, "max_tokens": 4096},
            "providers": {
                "openai-main": {
                    "type": "openai",
                    "api_key": "sk-openai",
                    "api_base": "https://api.openai.com/v1",
                    "organization": "org-123",
                },
                "anthropic-main": {
                    "type": "anthropic",
                    "api_key": "ant-key",
                    "api_base": "https://api.anthropic.com",
                },
                "azure-main": {
                    "type": "azure",
                    "api_key": "az-key",
                    "api_base": "https://my.azure.com/",
                    "api_version": "2024-02-01",
                },
                "litellm-main": {"type": "litellm", "api_key": "lt-key"},
                "no-key": {"type": "openai"},
            },
            "models": {
                "gpt4o": {
                    "provider": "openai-main",
                    "model": "gpt-4o",
                    "temperature": 0.3,
                    "max_tokens": 2048,
                    "timeout": 30,
                    "top_p": 0.9,
                    "stop": ["\\n\\n"],
                    "seed": 42,
                    "response_format": {"type": "json_object"},
                },
                "claude": {
                    "provider": "anthropic-main",
                    "model": "claude-3-5-sonnet",
                },
                "azure-gpt": {
                    "provider": "azure-main",
                    "model": "gpt-4o-deploy",
                },
                "litellm-model": {
                    "provider": "litellm-main",
                    "model": "custom/my-model",
                    "temperature": 0.5,
                    "max_tokens": 1024,
                    "timeout": 60,
                },
                "minimal": {
                    "provider": "no-key",
                    "model": "gpt-4o-mini",
                },
            },
            "aliases": {"smart": "gpt4o", "reasoning": "claude"},
        }
    )


# ============================================================
# to_params()
# ============================================================


class TestToParams:
    def test_openai_model_name(self, config):
        params = config.to_params("gpt4o")
        assert params["model"] == "gpt-4o"

    def test_openai_includes_api_key(self, config):
        params = config.to_params("gpt4o")
        assert params["api_key"] == "sk-openai"

    def test_openai_includes_base_url(self, config):
        params = config.to_params("gpt4o")
        assert "base_url" in params
        assert "api.openai.com" in params["base_url"]

    def test_openai_includes_organization(self, config):
        params = config.to_params("gpt4o")
        assert params["organization"] == "org-123"

    def test_openai_all_model_fields(self, config):
        params = config.to_params("gpt4o")
        assert params["temperature"] == 0.3
        assert params["max_tokens"] == 2048
        assert params["timeout"] == 30
        assert params["top_p"] == 0.9
        assert params["stop"] == ["\\n\\n"]
        assert params["seed"] == 42
        assert params["response_format"] == {"type": "json_object"}

    def test_anthropic_includes_api_key(self, config):
        params = config.to_params("claude")
        assert params["api_key"] == "ant-key"

    def test_anthropic_includes_base_url(self, config):
        params = config.to_params("claude")
        assert "base_url" in params

    def test_anthropic_uses_defaults(self, config):
        """Anthropic model with no model-level params uses global defaults."""
        params = config.to_params("claude")
        assert params["temperature"] == 0.7
        assert params["max_tokens"] == 4096

    def test_azure_includes_api_version(self, config):
        params = config.to_params("azure-gpt")
        assert params["api_version"] == "2024-02-01"

    def test_azure_includes_api_key(self, config):
        params = config.to_params("azure-gpt")
        assert params["api_key"] == "az-key"

    def test_filters_none_values(self, config):
        params = config.to_params("gpt4o")
        for v in params.values():
            assert v is not None

    def test_no_key_provider(self, config):
        params = config.to_params("minimal")
        assert "api_key" not in params
        assert "base_url" not in params

    def test_via_alias(self, config):
        params = config.to_params("smart")
        assert params["model"] == "gpt-4o"
        assert params["temperature"] == 0.3

    def test_uses_base_url_not_api_base(self, config):
        """to_params() outputs 'base_url' (OpenAI SDK format), not 'api_base'."""
        params = config.to_params("gpt4o")
        assert "base_url" in params
        assert "api_base" not in params

    def test_litellm_provider_params(self, config):
        params = config.to_params("litellm-model")
        assert params["api_key"] == "lt-key"
        assert params["temperature"] == 0.5


# ============================================================
# to_litellm_params()
# ============================================================


class TestToLitellmParams:
    def test_openai_prefix(self, config):
        params = config.to_litellm_params("gpt4o")
        assert params["model"] == "openai/gpt-4o"

    def test_anthropic_prefix(self, config):
        params = config.to_litellm_params("claude")
        assert params["model"] == "anthropic/claude-3-5-sonnet"

    def test_azure_prefix(self, config):
        params = config.to_litellm_params("azure-gpt")
        assert params["model"] == "azure/gpt-4o-deploy"

    def test_litellm_no_prefix(self, config):
        params = config.to_litellm_params("litellm-model")
        assert params["model"] == "custom/my-model"

    def test_uses_api_base_not_base_url(self, config):
        """LiteLLM uses 'api_base', not 'base_url'."""
        params = config.to_litellm_params("gpt4o")
        assert "api_base" in params
        assert "base_url" not in params

    def test_includes_temperature(self, config):
        params = config.to_litellm_params("gpt4o")
        assert params["temperature"] == 0.3

    def test_includes_max_tokens(self, config):
        params = config.to_litellm_params("gpt4o")
        assert params["max_tokens"] == 2048

    def test_includes_timeout(self, config):
        params = config.to_litellm_params("gpt4o")
        assert params["timeout"] == 30

    def test_filters_none_values(self, config):
        params = config.to_litellm_params("claude")
        for v in params.values():
            assert v is not None

    def test_no_api_base_when_none(self, config):
        params = config.to_litellm_params("litellm-model")
        assert "api_base" not in params

    def test_via_alias(self, config):
        params = config.to_litellm_params("smart")
        assert params["model"] == "openai/gpt-4o"

    def test_does_not_include_top_p(self, config):
        """to_litellm_params excludes top_p (unlike to_dspy_params)."""
        params = config.to_litellm_params("gpt4o")
        assert "top_p" not in params

    def test_does_not_include_stop(self, config):
        params = config.to_litellm_params("gpt4o")
        assert "stop" not in params

    def test_does_not_include_seed(self, config):
        params = config.to_litellm_params("gpt4o")
        assert "seed" not in params

    def test_does_not_include_response_format(self, config):
        params = config.to_litellm_params("gpt4o")
        assert "response_format" not in params


# ============================================================
# list_models / list_aliases
# ============================================================


class TestListMethods:
    def test_list_models_includes_all_models(self, config):
        models = config.list_models()
        for name in ("gpt4o", "claude", "azure-gpt", "litellm-model", "minimal"):
            assert name in models

    def test_list_models_includes_aliases(self, config):
        models = config.list_models()
        assert "smart" in models
        assert "reasoning" in models

    def test_list_models_no_duplicates(self, config):
        models = config.list_models()
        assert len(models) == len(set(models))

    def test_list_aliases_returns_dict(self, config):
        aliases = config.list_aliases()
        assert isinstance(aliases, dict)
        assert aliases["smart"] == "gpt4o"
        assert aliases["reasoning"] == "claude"

    def test_list_aliases_size(self, config):
        aliases = config.list_aliases()
        assert len(aliases) == 2

    def test_list_models_empty_config(self):
        cfg = LLMConfig({"version": "1"})
        assert cfg.list_models() == []
        assert cfg.list_aliases() == {}
