"""Unit tests for pai_llm_config DSPy integration -- to_dspy_params() and create_dspy_client()."""

import sys

import pytest
from unittest.mock import MagicMock, patch

from pai_llm_config.config import LLMConfig
from pai_llm_config.clients.factory import ClientCreationError


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def config():
    return LLMConfig(
        {
            "version": "1",
            "providers": {
                "openai-main": {
                    "type": "openai",
                    "api_key": "sk-openai",
                    "api_base": "https://api.openai.com/v1",
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
                    "max_tokens": 4096,
                    "top_p": 0.9,
                    "stop": ["\n\n"],
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
                },
                "minimal": {
                    "provider": "no-key",
                    "model": "gpt-4o-mini",
                },
            },
            "aliases": {"smart": "gpt4o"},
        }
    )


# ============================================================
# TestToDspyParams
# ============================================================


class TestToDspyParams:
    def test_openai_model_prefix(self, config):
        params = config.to_dspy_params("gpt4o")
        assert params["model"] == "openai/gpt-4o"

    def test_anthropic_model_prefix(self, config):
        params = config.to_dspy_params("claude")
        assert params["model"] == "anthropic/claude-3-5-sonnet"

    def test_azure_model_prefix(self, config):
        params = config.to_dspy_params("azure-gpt")
        assert params["model"] == "azure/gpt-4o-deploy"

    def test_litellm_no_prefix(self, config):
        params = config.to_dspy_params("litellm-model")
        assert params["model"] == "custom/my-model"

    def test_includes_api_key_and_base(self, config):
        params = config.to_dspy_params("gpt4o")
        assert params["api_key"] == "sk-openai"
        assert "api.openai.com" in params["api_base"]

    def test_includes_model_params(self, config):
        params = config.to_dspy_params("gpt4o")
        assert params["temperature"] == 0.3
        assert params["max_tokens"] == 4096
        assert params["top_p"] == 0.9
        assert params["stop"] == ["\n\n"]

    def test_no_none_values(self, config):
        params = config.to_dspy_params("claude")
        assert all(v is not None for v in params.values())
        assert "temperature" not in params
        assert "top_p" not in params

    def test_no_key_omits_api_key(self, config):
        params = config.to_dspy_params("minimal")
        assert "api_key" not in params
        assert "api_base" not in params

    def test_via_alias(self, config):
        params = config.to_dspy_params("smart")
        assert params["model"] == "openai/gpt-4o"
        assert params["temperature"] == 0.3

    def test_uses_api_base_not_base_url(self, config):
        """DSPy/LiteLLM uses api_base, not base_url."""
        params = config.to_dspy_params("gpt4o")
        assert "api_base" in params
        assert "base_url" not in params


# ============================================================
# TestCreateDspyClient
# ============================================================


class TestCreateDspyClient:
    def test_missing_sdk_raises(self, config):
        with patch.dict(sys.modules, {"dspy": None}):
            with pytest.raises(ClientCreationError, match="dspy package is required"):
                config.create_dspy_client("gpt4o")

    def test_returns_dspy_module(self, config):
        mock_dspy = MagicMock()
        mock_lm = MagicMock()
        mock_dspy.LM.return_value = mock_lm

        with patch.dict(sys.modules, {"dspy": mock_dspy}):
            result = config.create_dspy_client("gpt4o")

        # Returns the dspy module itself, not dspy.LM
        assert result is mock_dspy

    def test_calls_configure(self, config):
        mock_dspy = MagicMock()
        mock_lm = MagicMock()
        mock_dspy.LM.return_value = mock_lm

        with patch.dict(sys.modules, {"dspy": mock_dspy}):
            config.create_dspy_client("gpt4o")

        mock_dspy.configure.assert_called_once_with(lm=mock_lm)

    def test_lm_params_correct(self, config):
        mock_dspy = MagicMock()

        with patch.dict(sys.modules, {"dspy": mock_dspy}):
            config.create_dspy_client("gpt4o")

        kwargs = mock_dspy.LM.call_args[1]
        assert kwargs["model"] == "openai/gpt-4o"
        assert kwargs["api_key"] == "sk-openai"
        assert kwargs["temperature"] == 0.3

    def test_extra_kwargs_forwarded(self, config):
        mock_dspy = MagicMock()

        with patch.dict(sys.modules, {"dspy": mock_dspy}):
            config.create_dspy_client("gpt4o", cache=False, num_retries=5)

        kwargs = mock_dspy.LM.call_args[1]
        assert kwargs["cache"] is False
        assert kwargs["num_retries"] == 5

    def test_kwargs_override_defaults(self, config):
        mock_dspy = MagicMock()

        with patch.dict(sys.modules, {"dspy": mock_dspy}):
            config.create_dspy_client("gpt4o", temperature=0.9)

        kwargs = mock_dspy.LM.call_args[1]
        assert kwargs["temperature"] == 0.9
