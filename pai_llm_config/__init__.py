import threading
import sys
from pathlib import Path
from typing import Optional, Union, Dict, List, Any
from functools import wraps

# Main LLMConfig class and Pydantic models
from .config import LLMConfig
from .models import LLMConfigSchema, ModelConfig, ProviderConfig, AliasConfig

# Error types
from .config import (
    ConfigValidationError,
    ModelNotFoundError,
    ProviderNotFoundError,
    AliasConflictError,
    ModelTypeMismatchError,
)
from .clients.factory import ClientCreationError
from .keypool.pool import KeyPoolExhaustedError


class _ConfigSingleton:
    """Global singleton for LLMConfig, providing lazy loading and convenient access.

    Usage::

        from pai_llm_config import config

        model = config.get("smart")        # Get model config
        params = config.params("smart")    # Get SDK params dict
        client = config.openai_client("smart")  # Get OpenAI client
    """

    _config: Optional[LLMConfig] = None
    _lock: threading.Lock = threading.Lock()
    sys = sys  # Expose for tests

    def _get_config(self) -> LLMConfig:
        """Lazily loads the configuration if not already loaded."""
        if self._config is None:
            with self._lock:
                if self._config is None:
                    self._config = LLMConfig.default()
        return self._config

    def reload(self, **kwargs):
        """Forces a reload of the configuration."""
        with self._lock:
            LLMConfig.reset_default()
            self._config = LLMConfig.load(**kwargs)

    def configure(self, config_instance: LLMConfig):
        """Manually injects an LLMConfig instance (useful for testing)."""
        with self._lock:
            self._config = config_instance

    # --- Proxy methods to LLMConfig for easy access ---

    # L1: Config access
    def get(self, model_alias_or_name: str) -> ModelConfig:
        return self._get_config().get(model_alias_or_name)

    def params(self, model_alias_or_name: str) -> dict:
        return self._get_config().to_params(model_alias_or_name)

    def litellm_params(self, model_alias_or_name: str) -> dict:
        return self._get_config().to_litellm_params(model_alias_or_name)

    def dspy_params(self, model_alias_or_name: str) -> dict:
        return self._get_config().to_dspy_params(model_alias_or_name)

    def list_models(self) -> List[str]:
        return self._get_config().list_models()

    def list_aliases(self) -> Dict[str, str]:
        return self._get_config().list_aliases()

    # L2: SDK client factory
    def create_client(self, model_alias_or_name: str, **kwargs):
        return self._get_config().create_client(model_alias_or_name, **kwargs)

    def openai_client(self, model_alias_or_name: str):
        return self._get_config().create_openai_client(model_alias_or_name)

    def async_openai_client(self, model_alias_or_name: str):
        return self._get_config().create_async_openai_client(model_alias_or_name)

    def anthropic_client(self, model_alias_or_name: str):
        return self._get_config().create_anthropic_client(model_alias_or_name)

    def async_anthropic_client(self, model_alias_or_name: str):
        return self._get_config().create_async_anthropic_client(model_alias_or_name)

    def litellm_client(self, model_alias_or_name: str, **kwargs):
        return self._get_config().create_litellm_client(model_alias_or_name, **kwargs)

    def dspy_client(self, model_alias_or_name: str, **kwargs):
        return self._get_config().create_dspy_client(model_alias_or_name, **kwargs)

    # L2: Streaming
    def stream_openai_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        return self._get_config().stream_openai_chat(model_alias_or_name, messages, **kwargs)

    def async_stream_openai_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        return self._get_config().async_stream_openai_chat(model_alias_or_name, messages, **kwargs)

    def stream_anthropic_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        return self._get_config().stream_anthropic_chat(model_alias_or_name, messages, **kwargs)

    def async_stream_anthropic_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        return self._get_config().async_stream_anthropic_chat(model_alias_or_name, messages, **kwargs)

    def stream_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        return self._get_config().stream_chat(model_alias_or_name, messages, **kwargs)

    # Routing
    def route(self, task_type: str) -> ModelConfig:
        return self._get_config().route(task_type)

    def route_by(self, **kwargs) -> ModelConfig:
        return self._get_config().route_by(**kwargs)


config = _ConfigSingleton()

__all__ = [
    "LLMConfig",
    "ConfigValidationError",
    "ModelNotFoundError",
    "ProviderNotFoundError",
    "AliasConflictError",
    "ModelTypeMismatchError",
    "ClientCreationError",
    "KeyPoolExhaustedError",
    "config",
    "ModelConfig",
    "ProviderConfig",
    "AliasConfig",
    "LLMConfigSchema",
]
