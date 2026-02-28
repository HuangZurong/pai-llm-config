"""Stream wrappers with transparent usage reporting to KeyPool."""

import logging
from typing import Any, Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from ..keypool.pool import KeyPool

logger = logging.getLogger("pai_llm_config")


class OpenAIStreamWrapper:
    """Wraps an OpenAI Stream[ChatCompletionChunk] to auto-report usage on completion.

    Usage:
        stream = factory.stream_openai_chat("gpt4o", messages=[...])
        for chunk in stream:
            print(chunk.choices[0].delta.content or "", end="")
        # Usage auto-reported when iteration ends.

    Also supports context manager:
        with factory.stream_openai_chat("gpt4o", messages=[...]) as stream:
            for chunk in stream:
                ...
    """

    def __init__(
        self,
        stream: Any,
        key_pool: "KeyPool",
        api_key: str,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
    ):
        self._stream = stream
        self._key_pool = key_pool
        self._api_key = api_key
        self._cost_per_1k_input = cost_per_1k_input
        self._cost_per_1k_output = cost_per_1k_output
        self._usage_reported = False

    def __iter__(self):
        try:
            for chunk in self._stream:
                if hasattr(chunk, "usage") and chunk.usage is not None:
                    self._report_usage(chunk.usage)
                yield chunk
        except Exception:
            self._report_error()
            raise
        finally:
            if not self._usage_reported:
                self._report_usage_fallback()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    def close(self):
        if hasattr(self._stream, "close"):
            self._stream.close()

    @property
    def response(self):
        """Access the underlying httpx.Response (passthrough from SDK stream)."""
        return getattr(self._stream, "response", None)

    def _report_usage(self, usage: Any):
        if self._usage_reported:
            return
        self._usage_reported = True
        total_tokens = getattr(usage, "total_tokens", 0) or 0
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        cost = self._calculate_cost(input_tokens, output_tokens)
        self._key_pool.report_success(self._api_key, tokens=total_tokens, cost_usd=cost)

    def _report_usage_fallback(self):
        if self._usage_reported:
            return
        self._usage_reported = True
        self._key_pool.report_success(self._api_key, tokens=0, cost_usd=0.0)

    def _report_error(self):
        if self._usage_reported:
            return
        self._usage_reported = True
        self._key_pool.report_error(self._api_key)

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        cost = 0.0
        if self._cost_per_1k_input:
            cost += (input_tokens / 1000.0) * self._cost_per_1k_input
        if self._cost_per_1k_output:
            cost += (output_tokens / 1000.0) * self._cost_per_1k_output
        return cost


class AsyncOpenAIStreamWrapper:
    """Async version of OpenAIStreamWrapper for AsyncOpenAI streaming.

    Usage:
        stream = await factory.async_stream_openai_chat("gpt4o", messages=[...])
        async for chunk in stream:
            print(chunk.choices[0].delta.content or "", end="")
    """

    def __init__(
        self,
        stream: Any,
        key_pool: "KeyPool",
        api_key: str,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
    ):
        self._stream = stream
        self._key_pool = key_pool
        self._api_key = api_key
        self._cost_per_1k_input = cost_per_1k_input
        self._cost_per_1k_output = cost_per_1k_output
        self._usage_reported = False

    async def __aiter__(self):
        try:
            async for chunk in self._stream:
                if hasattr(chunk, "usage") and chunk.usage is not None:
                    self._report_usage(chunk.usage)
                yield chunk
        except Exception:
            self._report_error()
            raise
        finally:
            if not self._usage_reported:
                self._report_usage_fallback()

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.close()
        return False

    async def close(self):
        if hasattr(self._stream, "close"):
            result = self._stream.close()
            if hasattr(result, "__await__"):
                await result

    def _report_usage(self, usage: Any):
        if self._usage_reported:
            return
        self._usage_reported = True
        total_tokens = getattr(usage, "total_tokens", 0) or 0
        input_tokens = getattr(usage, "prompt_tokens", 0) or 0
        output_tokens = getattr(usage, "completion_tokens", 0) or 0
        cost = self._calculate_cost(input_tokens, output_tokens)
        self._key_pool.report_success(self._api_key, tokens=total_tokens, cost_usd=cost)

    def _report_usage_fallback(self):
        if self._usage_reported:
            return
        self._usage_reported = True
        self._key_pool.report_success(self._api_key, tokens=0, cost_usd=0.0)

    def _report_error(self):
        if self._usage_reported:
            return
        self._usage_reported = True
        self._key_pool.report_error(self._api_key)

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        cost = 0.0
        if self._cost_per_1k_input:
            cost += (input_tokens / 1000.0) * self._cost_per_1k_input
        if self._cost_per_1k_output:
            cost += (output_tokens / 1000.0) * self._cost_per_1k_output
        return cost


class AnthropicStreamWrapper:
    """Wraps an Anthropic MessageStream context manager with auto usage reporting.

    Usage:
        with factory.stream_anthropic_chat("claude", messages=[...], max_tokens=1024) as stream:
            for text in stream.text_stream:
                print(text, end="")
        # Usage auto-reported on __exit__.
    """

    def __init__(
        self,
        stream_cm: Any,
        key_pool: "KeyPool",
        api_key: str,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
    ):
        self._stream_cm = stream_cm
        self._stream = None
        self._key_pool = key_pool
        self._api_key = api_key
        self._cost_per_1k_input = cost_per_1k_input
        self._cost_per_1k_output = cost_per_1k_output
        self._usage_reported = False

    def __enter__(self):
        self._stream = self._stream_cm.__enter__()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self._report_error()
            else:
                self._extract_and_report_usage()
        finally:
            self._stream_cm.__exit__(exc_type, exc_val, exc_tb)
        return False

    @property
    def text_stream(self):
        """Proxy to the inner stream's text_stream iterator."""
        return self._stream.text_stream

    def get_final_message(self):
        """Proxy to inner stream's get_final_message()."""
        return self._stream.get_final_message()

    def get_final_text(self):
        """Proxy to inner stream's get_final_text()."""
        return self._stream.get_final_text()

    def _extract_and_report_usage(self):
        if self._usage_reported:
            return
        self._usage_reported = True
        try:
            message = self._stream.get_final_message()
            usage = message.usage
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            total = input_tokens + output_tokens
            cost = self._calculate_cost(input_tokens, output_tokens)
            self._key_pool.report_success(self._api_key, tokens=total, cost_usd=cost)
        except Exception:
            logger.warning("Failed to extract usage from Anthropic stream, reporting zero.")
            self._key_pool.report_success(self._api_key, tokens=0, cost_usd=0.0)

    def _report_error(self):
        if self._usage_reported:
            return
        self._usage_reported = True
        self._key_pool.report_error(self._api_key)

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        cost = 0.0
        if self._cost_per_1k_input:
            cost += (input_tokens / 1000.0) * self._cost_per_1k_input
        if self._cost_per_1k_output:
            cost += (output_tokens / 1000.0) * self._cost_per_1k_output
        return cost


class AsyncAnthropicStreamWrapper:
    """Async version of AnthropicStreamWrapper.

    Usage:
        async with factory.async_stream_anthropic_chat("claude", ...) as stream:
            async for text in stream.text_stream:
                print(text, end="")
    """

    def __init__(
        self,
        stream_cm: Any,
        key_pool: "KeyPool",
        api_key: str,
        cost_per_1k_input: float = 0.0,
        cost_per_1k_output: float = 0.0,
    ):
        self._stream_cm = stream_cm
        self._stream = None
        self._key_pool = key_pool
        self._api_key = api_key
        self._cost_per_1k_input = cost_per_1k_input
        self._cost_per_1k_output = cost_per_1k_output
        self._usage_reported = False

    async def __aenter__(self):
        self._stream = await self._stream_cm.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        try:
            if exc_type is not None:
                self._report_error()
            else:
                self._extract_and_report_usage()
        finally:
            await self._stream_cm.__aexit__(exc_type, exc_val, exc_tb)
        return False

    @property
    def text_stream(self):
        """Proxy to the inner stream's text_stream async iterator."""
        return self._stream.text_stream

    def get_final_message(self):
        """Proxy to inner stream's get_final_message()."""
        return self._stream.get_final_message()

    def get_final_text(self):
        """Proxy to inner stream's get_final_text()."""
        return self._stream.get_final_text()

    def _extract_and_report_usage(self):
        if self._usage_reported:
            return
        self._usage_reported = True
        try:
            message = self._stream.get_final_message()
            usage = message.usage
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            total = input_tokens + output_tokens
            cost = self._calculate_cost(input_tokens, output_tokens)
            self._key_pool.report_success(self._api_key, tokens=total, cost_usd=cost)
        except Exception:
            logger.warning("Failed to extract usage from Anthropic stream, reporting zero.")
            self._key_pool.report_success(self._api_key, tokens=0, cost_usd=0.0)

    def _report_error(self):
        if self._usage_reported:
            return
        self._usage_reported = True
        self._key_pool.report_error(self._api_key)

    def _calculate_cost(self, input_tokens: int, output_tokens: int) -> float:
        cost = 0.0
        if self._cost_per_1k_input:
            cost += (input_tokens / 1000.0) * self._cost_per_1k_input
        if self._cost_per_1k_output:
            cost += (output_tokens / 1000.0) * self._cost_per_1k_output
        return cost
