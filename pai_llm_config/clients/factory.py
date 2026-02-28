"""L2 SDK Client Factory - creates provider-specific SDK clients with key rotation."""

import threading
from typing import Any, Dict, Optional

from ..models import ModelConfig, ProviderConfig
from ..keypool.pool import KeyPool


class ClientCreationError(Exception):
    """Raised when a client cannot be created (e.g. missing SDK, wrong provider type)."""
    pass


class ClientFactory:
    """Creates SDK clients for each provider, wiring in key rotation via KeyPool.

    One KeyPool is created per provider and cached for the lifetime of this factory.
    """

    def __init__(
        self,
        providers: Dict[str, ProviderConfig],
        models: Dict[str, ModelConfig],
        aliases: Dict[str, str],  # alias_name -> model_name
    ):
        self._providers = providers
        self._models = models
        self._aliases = aliases
        self._key_pools: Dict[str, KeyPool] = {}
        self._pool_lock = threading.Lock()

    # --- Internal helpers ---

    def _resolve_model(self, model_alias_or_name: str) -> ModelConfig:
        name = self._aliases.get(model_alias_or_name, model_alias_or_name)
        model = self._models.get(name)
        if model is None:
            raise ClientCreationError(
                f"Model or alias '{model_alias_or_name}' not found."
            )
        return model

    def _get_key_pool(self, provider_name: str) -> KeyPool:
        """Lazily create and cache a KeyPool per provider (thread-safe)."""
        if provider_name not in self._key_pools:
            with self._pool_lock:
                if provider_name not in self._key_pools:
                    self._key_pools[provider_name] = KeyPool(
                        self._providers[provider_name]
                    )
        return self._key_pools[provider_name]

    def _get_api_key(self, provider_name: str) -> Optional[str]:
        """Get the next available API key from the pool, or None if no keys configured."""
        pool = self._get_key_pool(provider_name)
        if pool.size == 0:
            return None
        return pool.get_key()

    def _build_openai_kwargs(
        self, model: ModelConfig, provider: ProviderConfig
    ) -> Dict[str, Any]:
        """Build kwargs dict for openai.OpenAI / openai.AsyncOpenAI."""
        if provider.type not in ("openai", "azure", "litellm"):
            raise ClientCreationError(
                f"Provider '{model.provider}' is type '{provider.type}', "
                "not compatible with openai.OpenAI client."
            )
        kwargs: Dict[str, Any] = {}
        api_key = self._get_api_key(model.provider)
        if api_key:
            kwargs["api_key"] = api_key
        if provider.api_base:
            kwargs["base_url"] = str(provider.api_base)
        if provider.organization:
            kwargs["organization"] = provider.organization
        return kwargs

    def _build_anthropic_kwargs(
        self, model: ModelConfig, provider: ProviderConfig
    ) -> Dict[str, Any]:
        """Build kwargs dict for anthropic.Anthropic / anthropic.AsyncAnthropic."""
        if provider.type != "anthropic":
            raise ClientCreationError(
                f"Provider '{model.provider}' is type '{provider.type}', "
                "not compatible with anthropic.Anthropic client."
            )
        kwargs: Dict[str, Any] = {}
        api_key = self._get_api_key(model.provider)
        if api_key:
            kwargs["api_key"] = api_key
        if provider.api_base:
            kwargs["base_url"] = str(provider.api_base)
        return kwargs

    @staticmethod
    def _import_openai():
        try:
            import openai
            return openai
        except ImportError as e:
            raise ClientCreationError(
                "openai package is required. Install with: pip install openai"
            ) from e

    @staticmethod
    def _import_anthropic():
        try:
            import anthropic
            return anthropic
        except ImportError as e:
            raise ClientCreationError(
                "anthropic package is required. Install with: pip install anthropic"
            ) from e

    @staticmethod
    def _import_litellm():
        try:
            import litellm
            return litellm
        except ImportError as e:
            raise ClientCreationError(
                "litellm package is required. Install with: pip install litellm"
            ) from e

    @staticmethod
    def _import_dspy():
        try:
            import dspy
            return dspy
        except ImportError as e:
            raise ClientCreationError(
                "dspy package is required. Install with: pip install dspy"
            ) from e

    # --- Public factory methods ---

    def create_client(self, model_alias_or_name: str, **kwargs):
        """Create the appropriate SDK client based on provider type.

        Returns openai.OpenAI for openai/azure, litellm.Router for litellm,
        anthropic.Anthropic for anthropic.
        For type-safe usage prefer create_openai_client() / create_anthropic_client().
        """
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]
        if provider.type in ("openai", "azure"):
            return self.create_openai_client(model_alias_or_name)
        elif provider.type == "anthropic":
            return self.create_anthropic_client(model_alias_or_name)
        elif provider.type == "litellm":
            return self.create_litellm_client(model_alias_or_name, **kwargs)
        raise ClientCreationError(
            f"No default client type for provider '{provider.type}'. "
            "Use create_openai_client() or create_anthropic_client() explicitly."
        )

    def create_openai_client(self, model_alias_or_name: str):
        """Create an openai.OpenAI client with the resolved API key and base URL."""
        openai = self._import_openai()
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]
        kwargs = self._build_openai_kwargs(model, provider)
        return openai.OpenAI(**kwargs)

    def create_async_openai_client(self, model_alias_or_name: str):
        """Create an openai.AsyncOpenAI client with the resolved API key and base URL."""
        openai = self._import_openai()
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]
        kwargs = self._build_openai_kwargs(model, provider)
        return openai.AsyncOpenAI(**kwargs)

    def create_anthropic_client(self, model_alias_or_name: str):
        """Create an anthropic.Anthropic client with the resolved API key."""
        anthropic = self._import_anthropic()
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]
        kwargs = self._build_anthropic_kwargs(model, provider)
        return anthropic.Anthropic(**kwargs)

    def create_async_anthropic_client(self, model_alias_or_name: str):
        """Create an anthropic.AsyncAnthropic client with the resolved API key."""
        anthropic = self._import_anthropic()
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]
        kwargs = self._build_anthropic_kwargs(model, provider)
        return anthropic.AsyncAnthropic(**kwargs)

    def create_litellm_client(self, model_alias_or_name: str, **kwargs):
        """Create a litellm.Router pre-configured for this model.

        Returns a litellm.Router with .completion() and .acompletion() methods::

            client = config.litellm_client("smart")
            response = client.completion(model="smart", messages=[...])

        Extra kwargs are forwarded to litellm.Router().
        """
        litellm = self._import_litellm()
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]

        prefix_map = {
            "openai": "openai",
            "anthropic": "anthropic",
            "azure": "azure",
            "litellm": "",
        }
        prefix = prefix_map.get(provider.type, "")
        litellm_model = f"{prefix}/{model.model}" if prefix else model.model

        litellm_params: Dict[str, Any] = {"model": litellm_model}
        api_key = self._get_api_key(model.provider)
        if api_key:
            litellm_params["api_key"] = api_key
        if provider.api_base:
            litellm_params["api_base"] = str(provider.api_base)

        for field in ("temperature", "max_tokens", "timeout", "top_p", "stop", "seed"):
            val = getattr(model, field, None)
            if val is not None:
                litellm_params[field] = val

        model_list = [
            {
                "model_name": model_alias_or_name,
                "litellm_params": litellm_params,
            }
        ]

        return litellm.Router(model_list=model_list, **kwargs)

    def create_dspy_client(self, model_alias_or_name: str, **kwargs):
        """Create and configure a dspy environment for this model.

        Internally creates a dspy.LM, calls dspy.configure(lm=lm), and returns
        the dspy module itself — ready to use immediately::

            dspy = config.dspy_client("smart")
            qa = dspy.ChainOfThought("question -> answer")
            result = qa(question="Hello")

        Extra kwargs (cache, num_retries, etc.) are forwarded to dspy.LM().
        """
        dspy = self._import_dspy()
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]

        prefix_map = {"openai": "openai", "anthropic": "anthropic", "azure": "azure"}
        prefix = prefix_map.get(provider.type, "")
        model_name = f"{prefix}/{model.model}" if prefix else model.model

        params: Dict[str, Any] = {"model": model_name}
        api_key = self._get_api_key(model.provider)
        if api_key:
            params["api_key"] = api_key
        if provider.api_base:
            params["api_base"] = str(provider.api_base)

        for field in ("temperature", "max_tokens", "top_p", "stop"):
            val = getattr(model, field, None)
            if val is not None:
                params[field] = val

        params.update(kwargs)
        lm = dspy.LM(**params)
        dspy.configure(lm=lm)
        return dspy

    # --- Streaming convenience methods ---

    def _build_call_kwargs(self, model: ModelConfig, messages: list, **kwargs) -> Dict[str, Any]:
        """Build API call kwargs from model defaults + user overrides."""
        call_kwargs: Dict[str, Any] = {"model": model.model, "messages": messages}
        for field in ("temperature", "max_tokens", "timeout", "top_p", "stop", "seed"):
            if field not in kwargs:
                val = getattr(model, field, None)
                if val is not None:
                    call_kwargs[field] = val
        call_kwargs.update(kwargs)
        return call_kwargs

    def stream_openai_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        """Stream an OpenAI chat completion with automatic usage reporting.

        Auto-injects stream=True and stream_options={"include_usage": True}.
        Returns an OpenAIStreamWrapper that reports usage to KeyPool when iteration ends.
        """
        from .streaming import OpenAIStreamWrapper

        openai = self._import_openai()
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]
        client_kwargs = self._build_openai_kwargs(model, provider)
        api_key = client_kwargs.get("api_key", "")
        client = openai.OpenAI(**client_kwargs)

        call_kwargs = self._build_call_kwargs(model, messages, **kwargs)
        call_kwargs["stream"] = True
        call_kwargs.setdefault("stream_options", {})
        call_kwargs["stream_options"]["include_usage"] = True

        stream = client.chat.completions.create(**call_kwargs)
        pool = self._get_key_pool(model.provider)

        return OpenAIStreamWrapper(
            stream=stream,
            key_pool=pool,
            api_key=api_key,
            cost_per_1k_input=model.cost_per_1k_input or 0.0,
            cost_per_1k_output=model.cost_per_1k_output or 0.0,
        )

    async def async_stream_openai_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        """Async stream an OpenAI chat completion with automatic usage reporting."""
        from .streaming import AsyncOpenAIStreamWrapper

        openai = self._import_openai()
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]
        client_kwargs = self._build_openai_kwargs(model, provider)
        api_key = client_kwargs.get("api_key", "")
        client = openai.AsyncOpenAI(**client_kwargs)

        call_kwargs = self._build_call_kwargs(model, messages, **kwargs)
        call_kwargs["stream"] = True
        call_kwargs.setdefault("stream_options", {})
        call_kwargs["stream_options"]["include_usage"] = True

        stream = await client.chat.completions.create(**call_kwargs)
        pool = self._get_key_pool(model.provider)

        return AsyncOpenAIStreamWrapper(
            stream=stream,
            key_pool=pool,
            api_key=api_key,
            cost_per_1k_input=model.cost_per_1k_input or 0.0,
            cost_per_1k_output=model.cost_per_1k_output or 0.0,
        )

    def stream_anthropic_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        """Stream an Anthropic chat with automatic usage reporting.

        Returns an AnthropicStreamWrapper context manager. Use as:
            with factory.stream_anthropic_chat("claude", messages=[...], max_tokens=1024) as stream:
                for text in stream.text_stream:
                    print(text, end="")
        """
        from .streaming import AnthropicStreamWrapper

        anthropic = self._import_anthropic()
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]
        client_kwargs = self._build_anthropic_kwargs(model, provider)
        api_key = client_kwargs.get("api_key", "")
        client = anthropic.Anthropic(**client_kwargs)

        call_kwargs = self._build_call_kwargs(model, messages, **kwargs)
        call_kwargs.pop("stream", None)  # Anthropic uses .stream() method, not param

        if "max_tokens" not in call_kwargs:
            raise ClientCreationError(
                f"Anthropic streaming requires 'max_tokens'. "
                f"Set it in model config or pass as kwarg."
            )

        stream_cm = client.messages.stream(**call_kwargs)
        pool = self._get_key_pool(model.provider)

        return AnthropicStreamWrapper(
            stream_cm=stream_cm,
            key_pool=pool,
            api_key=api_key,
            cost_per_1k_input=model.cost_per_1k_input or 0.0,
            cost_per_1k_output=model.cost_per_1k_output or 0.0,
        )

    async def async_stream_anthropic_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        """Async stream an Anthropic chat with automatic usage reporting."""
        from .streaming import AsyncAnthropicStreamWrapper

        anthropic = self._import_anthropic()
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]
        client_kwargs = self._build_anthropic_kwargs(model, provider)
        api_key = client_kwargs.get("api_key", "")
        client = anthropic.AsyncAnthropic(**client_kwargs)

        call_kwargs = self._build_call_kwargs(model, messages, **kwargs)
        call_kwargs.pop("stream", None)

        if "max_tokens" not in call_kwargs:
            raise ClientCreationError(
                f"Anthropic streaming requires 'max_tokens'. "
                f"Set it in model config or pass as kwarg."
            )

        stream_cm = client.messages.stream(**call_kwargs)
        pool = self._get_key_pool(model.provider)

        return AsyncAnthropicStreamWrapper(
            stream_cm=stream_cm,
            key_pool=pool,
            api_key=api_key,
            cost_per_1k_input=model.cost_per_1k_input or 0.0,
            cost_per_1k_output=model.cost_per_1k_output or 0.0,
        )

    def stream_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        """Auto-dispatch streaming by provider type.

        Returns OpenAIStreamWrapper for openai/azure, AnthropicStreamWrapper for anthropic.
        """
        model = self._resolve_model(model_alias_or_name)
        provider = self._providers[model.provider]
        if provider.type in ("openai", "azure"):
            return self.stream_openai_chat(model_alias_or_name, messages, **kwargs)
        elif provider.type == "anthropic":
            return self.stream_anthropic_chat(model_alias_or_name, messages, **kwargs)
        raise ClientCreationError(
            f"Streaming not supported for provider type '{provider.type}'."
        )

    def key_pool(self, provider_name: str) -> KeyPool:
        """Get (or create) the KeyPool for a specific provider."""
        if provider_name not in self._providers:
            raise ClientCreationError(
                f"Provider '{provider_name}' not found in configuration."
            )
        return self._get_key_pool(provider_name)
