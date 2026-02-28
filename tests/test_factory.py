"""Unit tests for pai_llm_config.clients.factory -- ClientFactory with mocked SDKs."""

import sys

import pytest
from unittest.mock import MagicMock, patch

from pai_llm_config.models import ModelConfig, ProviderConfig, KeyConfig
from pai_llm_config.clients.factory import ClientFactory, ClientCreationError
from pai_llm_config.keypool.pool import KeyPool
from pai_llm_config.keypool.strategies import KeyEntry


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def providers():
    return {
        "openai-main": ProviderConfig(
            type="openai", api_key="sk-openai", api_base="https://api.openai.com/v1",
            organization="org-test",
        ),
        "anthropic-main": ProviderConfig(
            type="anthropic", api_key="ant-key", api_base="https://api.anthropic.com",
        ),
        "azure-main": ProviderConfig(
            type="azure", api_key="az-key", api_base="https://my.azure.com/",
            api_version="2024-02-01",
        ),
        "litellm-main": ProviderConfig(
            type="litellm", api_key="lt-key", api_base="https://litellm.proxy.com",
        ),
        "no-key": ProviderConfig(type="openai"),
        "multi-key": ProviderConfig(
            type="openai",
            api_keys=[
                KeyConfig(key="sk-a", alias="a", priority=1),
                KeyConfig(key="sk-b", alias="b", priority=2),
            ],
        ),
    }


@pytest.fixture
def models():
    return {
        "gpt4o": ModelConfig(provider="openai-main", model="gpt-4o", temperature=0.3, max_tokens=4096, timeout=30),
        "claude-sonnet": ModelConfig(provider="anthropic-main", model="claude-3-5-sonnet-20241022"),
        "gpt4o-azure": ModelConfig(provider="azure-main", model="gpt-4o-deploy"),
        "litellm-model": ModelConfig(provider="litellm-main", model="custom/my-model"),
        "no-key-model": ModelConfig(provider="no-key", model="gpt-4o"),
        "multi-key-model": ModelConfig(provider="multi-key", model="gpt-4o"),
    }


@pytest.fixture
def aliases():
    return {"smart": "gpt4o", "chat": "claude-sonnet"}


@pytest.fixture
def factory(providers, models, aliases):
    return ClientFactory(providers=providers, models=models, aliases=aliases)


@pytest.fixture
def mock_openai():
    mod = MagicMock()
    mod.OpenAI = MagicMock(name="OpenAI")
    mod.AsyncOpenAI = MagicMock(name="AsyncOpenAI")
    return mod


@pytest.fixture
def mock_anthropic():
    mod = MagicMock()
    mod.Anthropic = MagicMock(name="Anthropic")
    mod.AsyncAnthropic = MagicMock(name="AsyncAnthropic")
    return mod


# ============================================================
# TestResolveModel
# ============================================================


class TestResolveModel:
    def test_by_name(self, factory):
        m = factory._resolve_model("gpt4o")
        assert m.model == "gpt-4o"

    def test_by_alias(self, factory):
        m = factory._resolve_model("smart")
        assert m.model == "gpt-4o"

    def test_unknown_raises(self, factory):
        with pytest.raises(ClientCreationError, match="not found"):
            factory._resolve_model("nonexistent")

    def test_alias_resolves_to_model_not_alias(self, factory):
        m = factory._resolve_model("chat")
        assert m.model == "claude-3-5-sonnet-20241022"


# ============================================================
# TestCreateOpenAIClient
# ============================================================


class TestCreateOpenAIClient:
    def test_creates_with_params(self, factory, mock_openai):
        with patch.dict(sys.modules, {"openai": mock_openai}):
            factory.create_openai_client("gpt4o")
        mock_openai.OpenAI.assert_called_once()
        kwargs = mock_openai.OpenAI.call_args[1]
        assert kwargs["api_key"] == "sk-openai"
        assert "api.openai.com" in kwargs["base_url"]
        assert kwargs["organization"] == "org-test"

    def test_via_alias(self, factory, mock_openai):
        with patch.dict(sys.modules, {"openai": mock_openai}):
            factory.create_openai_client("smart")
        mock_openai.OpenAI.assert_called_once()

    def test_azure_compatible(self, factory, mock_openai):
        with patch.dict(sys.modules, {"openai": mock_openai}):
            factory.create_openai_client("gpt4o-azure")
        mock_openai.OpenAI.assert_called_once()
        kwargs = mock_openai.OpenAI.call_args[1]
        assert kwargs["api_key"] == "az-key"

    def test_anthropic_provider_raises(self, factory, mock_openai):
        with patch.dict(sys.modules, {"openai": mock_openai}):
            with pytest.raises(ClientCreationError, match="not compatible with openai"):
                factory.create_openai_client("claude-sonnet")

    def test_missing_sdk_raises(self, factory):
        with patch.dict(sys.modules, {"openai": None}):
            with pytest.raises(ClientCreationError, match="openai package is required"):
                factory.create_openai_client("gpt4o")

    def test_no_api_key(self, factory, mock_openai):
        with patch.dict(sys.modules, {"openai": mock_openai}):
            factory.create_openai_client("no-key-model")
        kwargs = mock_openai.OpenAI.call_args[1]
        assert "api_key" not in kwargs


# ============================================================
# TestCreateAsyncOpenAIClient
# ============================================================


class TestCreateAsyncOpenAIClient:
    def test_creates_async_client(self, factory, mock_openai):
        with patch.dict(sys.modules, {"openai": mock_openai}):
            factory.create_async_openai_client("gpt4o")
        mock_openai.AsyncOpenAI.assert_called_once()
        kwargs = mock_openai.AsyncOpenAI.call_args[1]
        assert kwargs["api_key"] == "sk-openai"

    def test_anthropic_provider_raises(self, factory, mock_openai):
        with patch.dict(sys.modules, {"openai": mock_openai}):
            with pytest.raises(ClientCreationError, match="not compatible"):
                factory.create_async_openai_client("claude-sonnet")

    def test_missing_sdk_raises(self, factory):
        with patch.dict(sys.modules, {"openai": None}):
            with pytest.raises(ClientCreationError, match="openai package is required"):
                factory.create_async_openai_client("gpt4o")


# ============================================================
# TestCreateAnthropicClient
# ============================================================


class TestCreateAnthropicClient:
    def test_creates_with_params(self, factory, mock_anthropic):
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            factory.create_anthropic_client("claude-sonnet")
        mock_anthropic.Anthropic.assert_called_once_with(
            api_key="ant-key",
            base_url="https://api.anthropic.com/",
        )

    def test_via_alias(self, factory, mock_anthropic):
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            factory.create_anthropic_client("chat")
        mock_anthropic.Anthropic.assert_called_once()

    def test_openai_provider_raises(self, factory, mock_anthropic):
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            with pytest.raises(ClientCreationError, match="not compatible with anthropic"):
                factory.create_anthropic_client("gpt4o")

    def test_missing_sdk_raises(self, factory):
        with patch.dict(sys.modules, {"anthropic": None}):
            with pytest.raises(ClientCreationError, match="anthropic package is required"):
                factory.create_anthropic_client("claude-sonnet")

    def test_no_api_key(self, factory, mock_anthropic, providers, models, aliases):
        providers["anthropic-nokey"] = ProviderConfig(type="anthropic")
        models["ant-nokey"] = ModelConfig(provider="anthropic-nokey", model="claude")
        f = ClientFactory(providers=providers, models=models, aliases=aliases)
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            f.create_anthropic_client("ant-nokey")
        kwargs = mock_anthropic.Anthropic.call_args[1]
        assert "api_key" not in kwargs


# ============================================================
# TestCreateAsyncAnthropicClient
# ============================================================


class TestCreateAsyncAnthropicClient:
    def test_creates_async_client(self, factory, mock_anthropic):
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            factory.create_async_anthropic_client("claude-sonnet")
        mock_anthropic.AsyncAnthropic.assert_called_once()

    def test_openai_provider_raises(self, factory, mock_anthropic):
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            with pytest.raises(ClientCreationError, match="not compatible"):
                factory.create_async_anthropic_client("gpt4o")

    def test_missing_sdk_raises(self, factory):
        with patch.dict(sys.modules, {"anthropic": None}):
            with pytest.raises(ClientCreationError, match="anthropic package is required"):
                factory.create_async_anthropic_client("claude-sonnet")


# ============================================================
# TestCreateLiteLLMClient
# ============================================================


class TestCreateLiteLLMClient:
    def test_returns_router(self, factory):
        mock_litellm = MagicMock()
        mock_router = MagicMock()
        mock_litellm.Router.return_value = mock_router
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            result = factory.create_litellm_client("gpt4o")
        assert result is mock_router

    def test_router_model_list_openai_prefix(self, factory):
        mock_litellm = MagicMock()
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            factory.create_litellm_client("gpt4o")
        call_kwargs = mock_litellm.Router.call_args[1]
        model_list = call_kwargs["model_list"]
        assert len(model_list) == 1
        assert model_list[0]["model_name"] == "gpt4o"
        assert model_list[0]["litellm_params"]["model"] == "openai/gpt-4o"
        assert model_list[0]["litellm_params"]["api_key"] == "sk-openai"

    def test_anthropic_provider_prefix(self, factory):
        mock_litellm = MagicMock()
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            factory.create_litellm_client("claude-sonnet")
        model_list = mock_litellm.Router.call_args[1]["model_list"]
        assert model_list[0]["litellm_params"]["model"] == "anthropic/claude-3-5-sonnet-20241022"

    def test_azure_provider_prefix(self, factory):
        mock_litellm = MagicMock()
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            factory.create_litellm_client("gpt4o-azure")
        model_list = mock_litellm.Router.call_args[1]["model_list"]
        assert model_list[0]["litellm_params"]["model"] == "azure/gpt-4o-deploy"

    def test_litellm_provider_no_prefix(self, factory):
        mock_litellm = MagicMock()
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            factory.create_litellm_client("litellm-model")
        model_list = mock_litellm.Router.call_args[1]["model_list"]
        assert model_list[0]["litellm_params"]["model"] == "custom/my-model"

    def test_via_alias(self, factory):
        mock_litellm = MagicMock()
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            factory.create_litellm_client("smart")
        model_list = mock_litellm.Router.call_args[1]["model_list"]
        assert model_list[0]["model_name"] == "smart"
        assert model_list[0]["litellm_params"]["model"] == "openai/gpt-4o"

    def test_includes_api_base(self, factory):
        mock_litellm = MagicMock()
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            factory.create_litellm_client("gpt4o")
        litellm_params = mock_litellm.Router.call_args[1]["model_list"][0]["litellm_params"]
        assert "api.openai.com" in litellm_params["api_base"]

    def test_extra_kwargs_forwarded(self, factory):
        mock_litellm = MagicMock()
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            factory.create_litellm_client("gpt4o", routing_strategy="simple-shuffle")
        call_kwargs = mock_litellm.Router.call_args[1]
        assert call_kwargs["routing_strategy"] == "simple-shuffle"

    def test_missing_sdk_raises(self, factory):
        with patch.dict(sys.modules, {"litellm": None}):
            with pytest.raises(ClientCreationError, match="litellm package is required"):
                factory.create_litellm_client("gpt4o")

    def test_includes_model_params(self, factory):
        """Model params (temperature, max_tokens, etc.) should be in litellm_params."""
        mock_litellm = MagicMock()
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            factory.create_litellm_client("gpt4o")
        litellm_params = mock_litellm.Router.call_args[1]["model_list"][0]["litellm_params"]
        assert litellm_params["temperature"] == 0.3
        assert litellm_params["max_tokens"] == 4096
        assert litellm_params["timeout"] == 30

    def test_omits_none_model_params(self, factory):
        """Model params that are None should not appear in litellm_params."""
        mock_litellm = MagicMock()
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            factory.create_litellm_client("claude-sonnet")
        litellm_params = mock_litellm.Router.call_args[1]["model_list"][0]["litellm_params"]
        assert "temperature" not in litellm_params
        assert "max_tokens" not in litellm_params


# ============================================================
# TestCreateClient (dispatch)
# ============================================================


class TestCreateClient:
    def test_openai_dispatches(self, factory, mock_openai):
        with patch.dict(sys.modules, {"openai": mock_openai}):
            factory.create_client("gpt4o")
        mock_openai.OpenAI.assert_called_once()

    def test_anthropic_dispatches(self, factory, mock_anthropic):
        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            factory.create_client("claude-sonnet")
        mock_anthropic.Anthropic.assert_called_once()

    def test_azure_dispatches_to_openai(self, factory, mock_openai):
        with patch.dict(sys.modules, {"openai": mock_openai}):
            factory.create_client("gpt4o-azure")
        mock_openai.OpenAI.assert_called_once()

    def test_litellm_dispatches_to_litellm_client(self, factory):
        mock_litellm = MagicMock()
        with patch.dict(sys.modules, {"litellm": mock_litellm}):
            result = factory.create_client("litellm-model")
        mock_litellm.Router.assert_called_once()


# ============================================================
# TestKeyPoolIntegration
# ============================================================


class TestKeyPoolIntegration:
    def test_pool_lazily_created(self, factory):
        assert "openai-main" not in factory._key_pools
        pool = factory.key_pool("openai-main")
        assert isinstance(pool, KeyPool)
        assert "openai-main" in factory._key_pools

    def test_pool_cached(self, factory):
        p1 = factory.key_pool("openai-main")
        p2 = factory.key_pool("openai-main")
        assert p1 is p2

    def test_unknown_provider_raises(self, factory):
        with pytest.raises(ClientCreationError, match="not found"):
            factory.key_pool("nonexistent")

    def test_multi_key_rotation(self, factory, mock_openai):
        with patch.dict(sys.modules, {"openai": mock_openai}):
            factory.create_openai_client("multi-key-model")
            factory.create_openai_client("multi-key-model")
        calls = mock_openai.OpenAI.call_args_list
        keys = [c[1]["api_key"] for c in calls]
        # Priority strategy: always picks sk-a (priority=1)
        assert keys == ["sk-a", "sk-a"]
