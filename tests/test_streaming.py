"""Unit tests for pai_llm_config.clients.streaming -- stream wrappers with usage reporting."""

import sys
import asyncio

import pytest
from unittest.mock import MagicMock, patch, AsyncMock

from pai_llm_config.models import ModelConfig, ProviderConfig, KeyConfig
from pai_llm_config.clients.factory import ClientFactory, ClientCreationError
from pai_llm_config.clients.streaming import (
    OpenAIStreamWrapper,
    AsyncOpenAIStreamWrapper,
    AnthropicStreamWrapper,
    AsyncAnthropicStreamWrapper,
)
from pai_llm_config.keypool.pool import KeyPool


# ============================================================
# Mock helpers
# ============================================================


class MockUsage:
    """Simulates OpenAI usage object on the final stream chunk."""

    def __init__(self, prompt_tokens=10, completion_tokens=20, total_tokens=30):
        self.prompt_tokens = prompt_tokens
        self.completion_tokens = completion_tokens
        self.total_tokens = total_tokens


class MockChunk:
    """Simulates an OpenAI ChatCompletionChunk."""

    def __init__(self, usage=None):
        self.usage = usage


class MockOpenAIStream:
    """Simulates openai.Stream[ChatCompletionChunk]."""

    def __init__(self, chunks):
        self._chunks = chunks
        self.closed = False

    def __iter__(self):
        return iter(self._chunks)

    def close(self):
        self.closed = True


class MockOpenAIStreamError:
    """Simulates a stream that raises mid-iteration."""

    def __init__(self, error_after=1):
        self._count = 0
        self._error_after = error_after
        self.closed = False

    def __iter__(self):
        for i in range(5):
            if i >= self._error_after:
                raise RuntimeError("Stream connection lost")
            yield MockChunk()

    def close(self):
        self.closed = True


class MockAsyncOpenAIStream:
    """Simulates openai.AsyncStream[ChatCompletionChunk]."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def __aiter__(self):
        for chunk in self._chunks:
            yield chunk

    async def close(self):
        pass


class MockAnthropicUsage:
    def __init__(self, input_tokens=50, output_tokens=100):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens


class MockAnthropicMessage:
    def __init__(self, input_tokens=50, output_tokens=100):
        self.usage = MockAnthropicUsage(input_tokens, output_tokens)


class MockAnthropicStreamInner:
    """Simulates the inner MessageStream object."""

    def __init__(self, texts, final_message):
        self.text_stream = iter(texts)
        self._final_message = final_message
        self._final_text = "".join(texts)

    def get_final_message(self):
        return self._final_message

    def get_final_text(self):
        return self._final_text


class MockAnthropicStreamCM:
    """Simulates the context manager from client.messages.stream()."""

    def __init__(self, texts=None, final_message=None):
        texts = texts or ["Hello", " world"]
        final_message = final_message or MockAnthropicMessage()
        self._inner = MockAnthropicStreamInner(texts, final_message)
        self._exited = False

    def __enter__(self):
        return self._inner

    def __exit__(self, *args):
        self._exited = True


class MockAsyncAnthropicStreamInner:
    """Async version of MockAnthropicStreamInner."""

    def __init__(self, texts, final_message):
        self._texts = texts
        self._final_message = final_message

    @property
    def text_stream(self):
        return self._async_text_iter()

    async def _async_text_iter(self):
        for text in self._texts:
            yield text

    def get_final_message(self):
        return self._final_message

    def get_final_text(self):
        return "".join(self._texts)


class MockAsyncAnthropicStreamCM:
    """Async context manager simulating client.messages.stream()."""

    def __init__(self, texts=None, final_message=None):
        texts = texts or ["Hello", " world"]
        final_message = final_message or MockAnthropicMessage()
        self._inner = MockAsyncAnthropicStreamInner(texts, final_message)

    async def __aenter__(self):
        return self._inner

    async def __aexit__(self, *args):
        pass


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def key_pool():
    """A real KeyPool with a single key for testing reporting."""
    provider = ProviderConfig(
        type="openai",
        api_keys=[KeyConfig(key="sk-test", alias="test", priority=1)],
    )
    return KeyPool(provider)


@pytest.fixture
def providers():
    return {
        "openai-main": ProviderConfig(
            type="openai", api_key="sk-openai", api_base="https://api.openai.com/v1",
        ),
        "anthropic-main": ProviderConfig(
            type="anthropic", api_key="ant-key", api_base="https://api.anthropic.com",
        ),
        "litellm-main": ProviderConfig(
            type="litellm", api_key="lt-key",
        ),
    }


@pytest.fixture
def models():
    return {
        "gpt4o": ModelConfig(
            provider="openai-main", model="gpt-4o",
            temperature=0.3, max_tokens=4096,
            cost_per_1k_input=0.0025, cost_per_1k_output=0.01,
        ),
        "claude": ModelConfig(
            provider="anthropic-main", model="claude-sonnet",
            max_tokens=1024,
        ),
        "claude-no-max": ModelConfig(
            provider="anthropic-main", model="claude-sonnet",
        ),
        "litellm-model": ModelConfig(
            provider="litellm-main", model="custom/model",
        ),
    }


@pytest.fixture
def aliases():
    return {"smart": "gpt4o"}


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
# TestOpenAIStreamWrapper
# ============================================================


class TestOpenAIStreamWrapper:
    def test_yields_all_chunks(self, key_pool):
        chunks = [MockChunk(), MockChunk(), MockChunk(usage=MockUsage())]
        stream = MockOpenAIStream(chunks)
        wrapper = OpenAIStreamWrapper(stream, key_pool, "sk-test")

        result = list(wrapper)
        assert len(result) == 3

    def test_extracts_usage_and_reports(self, key_pool):
        usage = MockUsage(prompt_tokens=100, completion_tokens=200, total_tokens=300)
        chunks = [MockChunk(), MockChunk(usage=usage)]
        stream = MockOpenAIStream(chunks)
        wrapper = OpenAIStreamWrapper(stream, key_pool, "sk-test")

        list(wrapper)

        status = key_pool.status()
        entry = status[0]
        assert entry["requests"] == 1
        assert entry["tokens"] == 300

    def test_reports_zero_when_no_usage(self, key_pool):
        chunks = [MockChunk(), MockChunk()]  # No usage on any chunk
        stream = MockOpenAIStream(chunks)
        wrapper = OpenAIStreamWrapper(stream, key_pool, "sk-test")

        list(wrapper)

        status = key_pool.status()
        entry = status[0]
        assert entry["requests"] == 1
        assert entry["tokens"] == 0

    def test_reports_error_on_exception(self, key_pool):
        stream = MockOpenAIStreamError(error_after=1)
        wrapper = OpenAIStreamWrapper(stream, key_pool, "sk-test")

        with pytest.raises(RuntimeError, match="connection lost"):
            list(wrapper)

        status = key_pool.status()
        entry = status[0]
        assert entry["healthy"] is True  # 1 error, not enough to mark unhealthy
        assert entry["requests"] == 0  # report_error doesn't increment requests

    def test_context_manager(self, key_pool):
        chunks = [MockChunk(usage=MockUsage())]
        stream = MockOpenAIStream(chunks)
        wrapper = OpenAIStreamWrapper(stream, key_pool, "sk-test")

        with wrapper as w:
            result = list(w)
        assert len(result) == 1
        assert stream.closed

    def test_cost_calculation(self, key_pool):
        usage = MockUsage(prompt_tokens=1000, completion_tokens=500, total_tokens=1500)
        chunks = [MockChunk(usage=usage)]
        stream = MockOpenAIStream(chunks)
        wrapper = OpenAIStreamWrapper(
            stream, key_pool, "sk-test",
            cost_per_1k_input=0.01, cost_per_1k_output=0.03,
        )

        list(wrapper)

        status = key_pool.status()
        entry = status[0]
        # cost = (1000/1000)*0.01 + (500/1000)*0.03 = 0.01 + 0.015 = 0.025
        assert entry["cost_usd"] == pytest.approx(0.025)

    def test_double_report_guard(self, key_pool):
        """Even if __iter__ reports and __exit__ fires, usage is reported only once."""
        usage = MockUsage(total_tokens=100)
        chunks = [MockChunk(usage=usage)]
        stream = MockOpenAIStream(chunks)
        wrapper = OpenAIStreamWrapper(stream, key_pool, "sk-test")

        with wrapper as w:
            list(w)

        status = key_pool.status()
        assert status[0]["requests"] == 1  # Not 2

    def test_close_delegates(self, key_pool):
        stream = MockOpenAIStream([])
        wrapper = OpenAIStreamWrapper(stream, key_pool, "sk-test")
        wrapper.close()
        assert stream.closed


# ============================================================
# TestAsyncOpenAIStreamWrapper
# ============================================================


class TestAsyncOpenAIStreamWrapper:
    @pytest.mark.asyncio
    async def test_async_yields_and_reports(self, key_pool):
        usage = MockUsage(total_tokens=50)
        chunks = [MockChunk(), MockChunk(usage=usage)]
        stream = MockAsyncOpenAIStream(chunks)
        wrapper = AsyncOpenAIStreamWrapper(stream, key_pool, "sk-test")

        result = []
        async for chunk in wrapper:
            result.append(chunk)
        assert len(result) == 2

        status = key_pool.status()
        assert status[0]["requests"] == 1
        assert status[0]["tokens"] == 50

    @pytest.mark.asyncio
    async def test_async_reports_error(self, key_pool):
        async def error_stream():
            yield MockChunk()
            raise RuntimeError("async error")

        stream = MagicMock()
        stream.__aiter__ = error_stream
        # Use the actual failing stream approach
        wrapper = AsyncOpenAIStreamWrapper(stream, key_pool, "sk-test")

        # Manually test the error path via the internal method
        wrapper._report_error()
        assert wrapper._usage_reported

    @pytest.mark.asyncio
    async def test_async_context_manager(self, key_pool):
        chunks = [MockChunk(usage=MockUsage())]
        stream = MockAsyncOpenAIStream(chunks)
        wrapper = AsyncOpenAIStreamWrapper(stream, key_pool, "sk-test")

        async with wrapper as w:
            result = []
            async for chunk in w:
                result.append(chunk)
        assert len(result) == 1


# ============================================================
# TestAnthropicStreamWrapper
# ============================================================


class TestAnthropicStreamWrapper:
    def test_context_manager_enters_and_exits(self, key_pool):
        cm = MockAnthropicStreamCM()
        wrapper = AnthropicStreamWrapper(cm, key_pool, "sk-test")

        with wrapper as w:
            texts = list(w.text_stream)
        assert texts == ["Hello", " world"]
        assert cm._exited

    def test_text_stream_proxy(self, key_pool):
        cm = MockAnthropicStreamCM(texts=["a", "b", "c"])
        wrapper = AnthropicStreamWrapper(cm, key_pool, "sk-test")

        with wrapper as w:
            result = list(w.text_stream)
        assert result == ["a", "b", "c"]

    def test_get_final_message_proxy(self, key_pool):
        msg = MockAnthropicMessage(input_tokens=10, output_tokens=20)
        cm = MockAnthropicStreamCM(final_message=msg)
        wrapper = AnthropicStreamWrapper(cm, key_pool, "sk-test")

        with wrapper as w:
            list(w.text_stream)
            message = w.get_final_message()
        assert message.usage.input_tokens == 10

    def test_extracts_usage_and_reports(self, key_pool):
        msg = MockAnthropicMessage(input_tokens=100, output_tokens=200)
        cm = MockAnthropicStreamCM(final_message=msg)
        wrapper = AnthropicStreamWrapper(cm, key_pool, "sk-test")

        with wrapper:
            pass

        status = key_pool.status()
        assert status[0]["requests"] == 1
        assert status[0]["tokens"] == 300  # 100 + 200

    def test_reports_error_on_exception(self, key_pool):
        cm = MockAnthropicStreamCM()
        wrapper = AnthropicStreamWrapper(cm, key_pool, "sk-test")

        with pytest.raises(ValueError):
            with wrapper:
                raise ValueError("test error")

        # Should have called report_error, not report_success
        status = key_pool.status()
        assert status[0]["requests"] == 0

    def test_graceful_degradation_on_usage_failure(self, key_pool):
        """If get_final_message() fails, report success with zero tokens."""
        cm = MockAnthropicStreamCM()
        # Make get_final_message raise
        cm._inner.get_final_message = MagicMock(side_effect=RuntimeError("no message"))
        wrapper = AnthropicStreamWrapper(cm, key_pool, "sk-test")

        with wrapper:
            pass

        status = key_pool.status()
        assert status[0]["requests"] == 1
        assert status[0]["tokens"] == 0

    def test_cost_calculation(self, key_pool):
        msg = MockAnthropicMessage(input_tokens=2000, output_tokens=1000)
        cm = MockAnthropicStreamCM(final_message=msg)
        wrapper = AnthropicStreamWrapper(
            cm, key_pool, "sk-test",
            cost_per_1k_input=0.003, cost_per_1k_output=0.015,
        )

        with wrapper:
            pass

        status = key_pool.status()
        # cost = (2000/1000)*0.003 + (1000/1000)*0.015 = 0.006 + 0.015 = 0.021
        assert status[0]["cost_usd"] == pytest.approx(0.021)


# ============================================================
# TestAsyncAnthropicStreamWrapper
# ============================================================


class TestAsyncAnthropicStreamWrapper:
    @pytest.mark.asyncio
    async def test_async_context_manager(self, key_pool):
        cm = MockAsyncAnthropicStreamCM()
        wrapper = AsyncAnthropicStreamWrapper(cm, key_pool, "sk-test")

        async with wrapper as w:
            texts = []
            async for text in w.text_stream:
                texts.append(text)
        assert texts == ["Hello", " world"]

    @pytest.mark.asyncio
    async def test_async_usage_reporting(self, key_pool):
        msg = MockAnthropicMessage(input_tokens=50, output_tokens=75)
        cm = MockAsyncAnthropicStreamCM(final_message=msg)
        wrapper = AsyncAnthropicStreamWrapper(cm, key_pool, "sk-test")

        async with wrapper:
            pass

        status = key_pool.status()
        assert status[0]["requests"] == 1
        assert status[0]["tokens"] == 125

    @pytest.mark.asyncio
    async def test_async_reports_error(self, key_pool):
        cm = MockAsyncAnthropicStreamCM()
        wrapper = AsyncAnthropicStreamWrapper(cm, key_pool, "sk-test")

        with pytest.raises(ValueError):
            async with wrapper:
                raise ValueError("async error")


# ============================================================
# TestFactoryStreamMethods
# ============================================================


class TestFactoryStreamMethods:
    def test_stream_openai_chat_injects_stream_params(self, factory, mock_openai):
        """stream=True and stream_options should be auto-injected."""
        mock_stream = MockOpenAIStream([MockChunk(usage=MockUsage())])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict(sys.modules, {"openai": mock_openai}):
            wrapper = factory.stream_openai_chat("gpt4o", messages=[{"role": "user", "content": "hi"}])
            list(wrapper)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["stream"] is True
        assert call_kwargs["stream_options"]["include_usage"] is True

    def test_stream_openai_chat_injects_model_defaults(self, factory, mock_openai):
        """Model defaults (temperature, max_tokens) should be injected."""
        mock_stream = MockOpenAIStream([MockChunk()])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict(sys.modules, {"openai": mock_openai}):
            wrapper = factory.stream_openai_chat("gpt4o", messages=[])
            list(wrapper)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.3
        assert call_kwargs["max_tokens"] == 4096
        assert call_kwargs["model"] == "gpt-4o"

    def test_stream_openai_user_kwargs_override(self, factory, mock_openai):
        """User-supplied kwargs should override model defaults."""
        mock_stream = MockOpenAIStream([MockChunk()])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict(sys.modules, {"openai": mock_openai}):
            wrapper = factory.stream_openai_chat(
                "gpt4o", messages=[], temperature=0.9, max_tokens=100,
            )
            list(wrapper)

        call_kwargs = mock_client.chat.completions.create.call_args[1]
        assert call_kwargs["temperature"] == 0.9
        assert call_kwargs["max_tokens"] == 100

    def test_stream_anthropic_requires_max_tokens(self, factory, mock_anthropic):
        """Should raise if max_tokens is not set in model config or kwargs."""
        mock_client = MagicMock()
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            with pytest.raises(ClientCreationError, match="max_tokens"):
                factory.stream_anthropic_chat("claude-no-max", messages=[])

    def test_stream_anthropic_chat_creates_wrapper(self, factory, mock_anthropic):
        """Should create AnthropicStreamWrapper when max_tokens is configured."""
        mock_cm = MockAnthropicStreamCM()
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_cm
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            wrapper = factory.stream_anthropic_chat("claude", messages=[])
        assert isinstance(wrapper, AnthropicStreamWrapper)

    def test_stream_chat_dispatches_openai(self, factory, mock_openai):
        mock_stream = MockOpenAIStream([MockChunk()])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict(sys.modules, {"openai": mock_openai}):
            wrapper = factory.stream_chat("gpt4o", messages=[])
        assert isinstance(wrapper, OpenAIStreamWrapper)

    def test_stream_chat_dispatches_anthropic(self, factory, mock_anthropic):
        mock_cm = MockAnthropicStreamCM()
        mock_client = MagicMock()
        mock_client.messages.stream.return_value = mock_cm
        mock_anthropic.Anthropic.return_value = mock_client

        with patch.dict(sys.modules, {"anthropic": mock_anthropic}):
            wrapper = factory.stream_chat("claude", messages=[])
        assert isinstance(wrapper, AnthropicStreamWrapper)

    def test_stream_chat_unsupported_provider(self, factory):
        with pytest.raises(ClientCreationError, match="not supported"):
            factory.stream_chat("litellm-model", messages=[])

    def test_stream_via_alias(self, factory, mock_openai):
        mock_stream = MockOpenAIStream([MockChunk()])
        mock_client = MagicMock()
        mock_client.chat.completions.create.return_value = mock_stream
        mock_openai.OpenAI.return_value = mock_client

        with patch.dict(sys.modules, {"openai": mock_openai}):
            wrapper = factory.stream_openai_chat("smart", messages=[])
        assert isinstance(wrapper, OpenAIStreamWrapper)
