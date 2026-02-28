import os
import re
import copy
from pathlib import Path
from typing import Any, Dict, Optional, Union, ClassVar, List
from functools import lru_cache
import threading

from pydantic import ValidationError

from .models import (
    LLMConfigSchema,
    ModelConfig,
    ProviderConfig,
    AliasConfig,
    ModelType,
    KeyConfig,
)
from .loader import ConfigLoader, ConfigLoaderError
from .resolver import ConfigResolver, ConfigResolverError

# Module-level placeholders for optional dependencies.
# Set by _find_root_path / _get_active_env when imports succeed.
# Tests can monkeypatch these via "pai_llm_config.config.project_utils" etc.
project_utils = None
Environment = None


class ConfigValidationError(Exception):
    """Custom exception for semantic configuration validation errors."""

    def __init__(self, errors):
        if isinstance(errors, str):
            self.errors = [errors]
            super().__init__(errors)
        else:
            self.errors = errors
            super().__init__("\n" + "\n".join(errors))


class ModelNotFoundError(ConfigValidationError):
    pass


class ProviderNotFoundError(ConfigValidationError):
    pass


class AliasConflictError(ConfigValidationError):
    pass


class ModelTypeMismatchError(ConfigValidationError):
    pass


class LLMConfig:
    """Unified configuration manager for LLM applications."""

    _instance: ClassVar[Optional["LLMConfig"]] = None
    _instance_lock: ClassVar[threading.Lock] = threading.Lock()

    def __init__(self, config_data: Dict[str, Any]):
        # Validate raw data with Pydantic schema first
        try:
            self._config_schema = LLMConfigSchema.model_validate(config_data)
        except ValidationError as e:
            # Join error messages for easier reading in tests
            error_msg = str(e).replace("\n", " ").replace("  ", " ")
            raise ConfigValidationError(
                f"Pydantic validation error: {error_msg}"
            ) from e

        self._providers: Dict[str, ProviderConfig] = self._config_schema.providers
        self._models: Dict[str, ModelConfig] = self._config_schema.models
        self._aliases: Dict[str, AliasConfig] = self._config_schema.aliases
        self._factory_lock = threading.Lock()

        self._perform_semantic_validation()

    @classmethod
    def load(
        cls,
        profile: Optional[str] = None,
        config_path: Optional[Union[str, Path]] = None,
        dotenv: bool = True,
        root_path: Optional[Union[str, Path]] = None,
    ) -> "LLMConfig":
        """
        Loads the LLM configuration from various sources.

        If config_path is not provided, it attempts auto-discovery.
        If profile is not provided, it attempts auto-discovery.
        """
        # 1. Determine root path
        effective_root_path = Path(root_path) if root_path else cls._find_root_path()

        # 2. Determine active profile
        # Clear the lru_cache so re-loading picks up new profile values
        cls._get_active_profile.cache_clear()
        effective_profile = profile if profile else cls._get_active_profile()

        # 3. Load raw config data
        loader = ConfigLoader(root_path=effective_root_path)
        raw_config_data = loader.load_config_data(
            config_path=config_path,
            profile=effective_profile,
            load_dotenv_file=dotenv,
        )

        # 4. Resolve environment variables
        resolver = ConfigResolver()
        resolved_config_data = resolver.resolve(raw_config_data)

        return cls(resolved_config_data)

    @classmethod
    def default(cls) -> "LLMConfig":
        """Return the default singleton instance (auto-loads llm-config.yaml on first call).

        Thread-safe lazy initialization. The instance is cached and reused
        across the entire process lifetime.

        Usage::

            from pai_llm_config import LLMConfig
            config = LLMConfig.default()
            model = config.get("smart")
        """
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls.load()
        return cls._instance

    @classmethod
    def reset_default(cls) -> None:
        """Reset the default singleton (mainly for testing)."""
        with cls._instance_lock:
            cls._instance = None

    def get(self, model_alias_or_name: str) -> ModelConfig:
        """Retrieves a ModelConfig by its name or alias.
        Resolves mappings → aliases → model name, then applies global defaults.
        """
        model_name = self._resolve_name(model_alias_or_name)
        model_config = self._models.get(model_name)
        if not model_config:
            raise ModelNotFoundError(
                f"Model or alias '{model_alias_or_name}' not found."
            )
        return self._apply_defaults(model_config)

    def _resolve_name(self, name: str) -> str:
        """Resolve mappings + aliases to the canonical model name."""
        # 1. External mapping (e.g. "openai/gpt-4" → internal name)
        if self._config_schema.mappings:
            mapped = self._config_schema.mappings.get(name)
            if mapped:
                name = mapped
        # 2. Alias → model name
        if name in self._aliases:
            name = self._aliases[name].root
        return name

    def _apply_defaults(self, model_config: ModelConfig) -> ModelConfig:
        """Merge global defaults into model config (model-level values take priority)."""
        defaults = self._config_schema.defaults
        # defaults is always a DefaultsConfig instance; skip if all fields are None
        if not any(
            getattr(defaults, f) is not None
            for f in ("temperature", "max_tokens", "timeout", "top_p", "stop", "seed", "response_format")
        ):
            return model_config
        merged = copy.deepcopy(model_config)
        for field in ("temperature", "max_tokens", "timeout", "top_p", "stop", "seed", "response_format"):
            if getattr(merged, field) is None and getattr(defaults, field) is not None:
                setattr(merged, field, getattr(defaults, field))
        return merged

    def list_models(self) -> List[str]:
        """Lists all registered model names and aliases."""
        return list(self._models.keys()) + list(self._aliases.keys())

    def list_aliases(self) -> Dict[str, str]:
        """Returns a dictionary of all aliases and their target models."""
        return {k: v.root for k, v in self._aliases.items()}

    def to_params(self, model_alias_or_name: str) -> Dict[str, Any]:
        """Converts a model config to a dictionary of parameters suitable for SDKs."""
        model_config = self.get(model_alias_or_name)
        provider_config = self._providers[model_config.provider]

        params: Dict[str, Any] = {
            "model": model_config.model,
            "temperature": model_config.temperature,
            "max_tokens": model_config.max_tokens,
            "timeout": model_config.timeout,
            "top_p": model_config.top_p,
            "stop": model_config.stop,
            "seed": model_config.seed,
            "response_format": model_config.response_format,
        }

        # Add provider-specific params — api_key is already resolved by ConfigResolver
        if provider_config.type in ("openai", "azure", "litellm"):
            params["api_key"] = provider_config.api_key
            params["base_url"] = (
                str(provider_config.api_base) if provider_config.api_base else None
            )
            if provider_config.type == "azure" and provider_config.api_version:
                params["api_version"] = provider_config.api_version
            if provider_config.organization:
                params["organization"] = provider_config.organization

        elif provider_config.type == "anthropic":
            params["api_key"] = provider_config.api_key
            params["base_url"] = (
                str(provider_config.api_base) if provider_config.api_base else None
            )

        # Filter out None values
        return {k: v for k, v in params.items() if v is not None}

    def to_litellm_params(self, model_alias_or_name: str) -> Dict[str, Any]:
        """Converts a model config to LiteLLM-compatible parameters."""
        model_config = self.get(model_alias_or_name)
        provider_config = self._providers[model_config.provider]

        litellm_model_name = model_config.model
        if provider_config.type == "openai":
            litellm_model_name = f"openai/{model_config.model}"
        elif provider_config.type == "anthropic":
            litellm_model_name = f"anthropic/{model_config.model}"
        elif provider_config.type == "azure":
            litellm_model_name = f"azure/{model_config.model}"

        params: Dict[str, Any] = {
            "model": litellm_model_name,
            "api_key": provider_config.api_key,
            "api_base": (
                str(provider_config.api_base) if provider_config.api_base else None
            ),
            "temperature": model_config.temperature,
            "max_tokens": model_config.max_tokens,
            "timeout": model_config.timeout,
        }

        return {k: v for k, v in params.items() if v is not None}

    def to_dspy_params(self, model_alias_or_name: str) -> Dict[str, Any]:
        """Converts a model config to DSPy-compatible parameters for dspy.LM().

        DSPy uses LiteLLM internally, so model names use "provider/model" format
        and api_base (not base_url).
        """
        model_config = self.get(model_alias_or_name)
        provider_config = self._providers[model_config.provider]

        # DSPy uses LiteLLM format: "provider/model-name"
        model_name = model_config.model
        prefix_map = {"openai": "openai", "anthropic": "anthropic", "azure": "azure"}
        prefix = prefix_map.get(provider_config.type, "")
        if prefix:
            model_name = f"{prefix}/{model_config.model}"

        params: Dict[str, Any] = {"model": model_name}
        if provider_config.api_key:
            params["api_key"] = provider_config.api_key
        if provider_config.api_base:
            params["api_base"] = str(provider_config.api_base)

        for field in ("temperature", "max_tokens", "top_p", "stop"):
            val = getattr(model_config, field, None)
            if val is not None:
                params[field] = val

        return params

    # --- L2: SDK Client Factory ---

    def _get_client_factory(self):
        """Lazily create and cache the ClientFactory (thread-safe)."""
        if not hasattr(self, "_client_factory"):
            with self._factory_lock:
                if not hasattr(self, "_client_factory"):
                    from .clients.factory import ClientFactory

                    aliases = {k: v.root for k, v in self._aliases.items()}
                    self._client_factory = ClientFactory(
                        providers=self._providers,
                        models=self._models,
                        aliases=aliases,
                    )
        return self._client_factory

    def create_client(self, model_alias_or_name: str, **kwargs):
        """Create an SDK client (OpenAI or Anthropic) with built-in Key rotation.

        For type-safe usage, prefer create_openai_client() or create_anthropic_client().
        """
        return self._get_client_factory().create_client(model_alias_or_name, **kwargs)

    def create_openai_client(self, model_alias_or_name: str):
        """Create an OpenAI SDK client with Key rotation. Returns openai.OpenAI."""
        return self._get_client_factory().create_openai_client(model_alias_or_name)

    def create_async_openai_client(self, model_alias_or_name: str):
        """Create an async OpenAI SDK client. Returns openai.AsyncOpenAI."""
        return self._get_client_factory().create_async_openai_client(
            model_alias_or_name
        )

    def create_anthropic_client(self, model_alias_or_name: str):
        """Create an Anthropic SDK client with Key rotation."""
        return self._get_client_factory().create_anthropic_client(model_alias_or_name)

    def create_async_anthropic_client(self, model_alias_or_name: str):
        """Create an async Anthropic SDK client."""
        return self._get_client_factory().create_async_anthropic_client(
            model_alias_or_name
        )

    def create_litellm_client(self, model_alias_or_name: str, **kwargs):
        """Create a litellm.Router pre-configured for this model.

        Requires: pip install litellm
        Extra kwargs are forwarded to litellm.Router().
        """
        return self._get_client_factory().create_litellm_client(
            model_alias_or_name, **kwargs
        )

    def create_dspy_client(self, model_alias_or_name: str, **kwargs):
        """Return the dspy module, pre-configured with a LM for this model.

        Requires: pip install dspy
        Extra kwargs (cache, num_retries, etc.) are forwarded to dspy.LM().
        """
        return self._get_client_factory().create_dspy_client(
            model_alias_or_name, **kwargs
        )

    def key_pool(self, provider_name: str):
        """Get the KeyPool for a specific provider."""
        return self._get_client_factory().key_pool(provider_name)

    # --- L2: Streaming ---

    def stream_openai_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        """Stream OpenAI chat completion with automatic usage reporting."""
        return self._get_client_factory().stream_openai_chat(
            model_alias_or_name, messages, **kwargs
        )

    async def async_stream_openai_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        """Async stream OpenAI chat completion with automatic usage reporting."""
        return await self._get_client_factory().async_stream_openai_chat(
            model_alias_or_name, messages, **kwargs
        )

    def stream_anthropic_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        """Stream Anthropic chat with automatic usage reporting."""
        return self._get_client_factory().stream_anthropic_chat(
            model_alias_or_name, messages, **kwargs
        )

    async def async_stream_anthropic_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        """Async stream Anthropic chat with automatic usage reporting."""
        return await self._get_client_factory().async_stream_anthropic_chat(
            model_alias_or_name, messages, **kwargs
        )

    def stream_chat(self, model_alias_or_name: str, messages: list, **kwargs):
        """Stream chat with auto provider dispatch and usage reporting."""
        return self._get_client_factory().stream_chat(
            model_alias_or_name, messages, **kwargs
        )

    # --- Placeholder for routing methods (P0/P1) ---
    def route(self, task_type: str) -> ModelConfig:
        """Routes a task type to a ModelConfig based on presets."""
        target_alias_or_name = self._config_schema.routing.presets.get(task_type)
        if not target_alias_or_name:
            raise ModelNotFoundError(
                f"No routing preset found for task type '{task_type}'."
            )
        return self.get(target_alias_or_name.root)

    def route_by(self, **kwargs) -> ModelConfig:
        """Routes to a ModelConfig based on conditions (P1)."""
        # This will be implemented in P1, for now just raise an error or return a default
        raise NotImplementedError(
            "Conditional routing (route_by) is not yet implemented (P1)."
        )

    def _perform_semantic_validation(self):
        errors: List[str] = []
        self._validate_model_providers(errors)
        self._validate_aliases(errors)
        self._validate_fallbacks(errors)
        self._validate_routing_rules(errors)
        if errors:
            raise ConfigValidationError(errors)

    def _validate_model_providers(self, errors: List[str]):
        for model_name, model_config in self._models.items():
            if model_config.provider not in self._providers:
                errors.append(
                    f"Model '{model_name}' references non-existent provider '{model_config.provider}'."
                )

    def _validate_aliases(self, errors: List[str]):
        for alias_name, alias_config in self._aliases.items():
            target_model_name = alias_config.root
            if target_model_name not in self._models:
                errors.append(
                    f"Alias '{alias_name}' references non-existent model '{target_model_name}'."
                )
            if alias_name in self._models:
                errors.append(
                    f"Alias '{alias_name}' conflicts with an existing model name. "
                    "Please choose a different alias."
                )
            # Heuristic: non-embedding alias should not point to an embedding model
            target = self._models.get(target_model_name)
            if (
                target
                and target.type == "embedding"
                and not alias_name.lower().endswith("embedding")
            ):
                errors.append(
                    f"Chat alias '{alias_name}' points to an embedding model '{target_model_name}'. "
                    "Embedding models are typically used via create_embedding_client()."
                )

    def _validate_fallbacks(self, errors: List[str]):
        for fallback_name, fallback_config in self._config_schema.fallbacks.items():
            for i, model_name in enumerate(fallback_config.root):
                if model_name not in self._models:
                    errors.append(
                        f"Fallback '{fallback_name}' at index {i} references non-existent model '{model_name}'."
                    )

    def _validate_routing_rules(self, errors: List[str]):
        for i, rule in enumerate(self._config_schema.routing.rules):
            if rule.use and rule.use not in self._models and rule.use not in self._aliases:
                errors.append(
                    f"Routing rule {i} references non-existent model or alias '{rule.use}'."
                )
            if rule.default and rule.default not in self._models and rule.default not in self._aliases:
                errors.append(
                    f"Routing rule {i} default references non-existent model or alias '{rule.default}'."
                )

    @classmethod
    def _find_root_path(cls) -> Path:
        global project_utils
        # 1. Explicit environment variable
        if root := os.environ.get("LLM_CONFIG_ROOT"):
            return Path(root)

        # 2. flashboot_core (if available)
        if project_utils is not None:
            return Path(project_utils.get_root_path())
        try:
            from flashboot_core.utils import project_utils as _pu

            project_utils = _pu
            return Path(project_utils.get_root_path())
        except ImportError:
            pass

        # 3. Built-in fallback - look for markers (e.g., pyproject.toml, .git)
        current_dir = Path.cwd()
        for parent in [current_dir] + list(current_dir.parents):
            if any(
                (parent / marker).exists()
                for marker in [".git", "pyproject.toml", "setup.py"]
            ):
                return parent
        return current_dir  # Fallback to current directory

    @classmethod
    @lru_cache(maxsize=1)  # Cache the active profile once
    def _get_active_profile(cls) -> Optional[str]:
        global Environment
        # 1. LLM_CONFIG_PROFILE environment variable
        if profile := os.environ.get("LLM_CONFIG_PROFILE"):
            return profile

        # 2. Fallback: LLM_CONFIG_ENV (backward compatibility)
        if profile := os.environ.get("LLM_CONFIG_ENV"):
            return profile

        # 3. flashboot_core (if available)
        if Environment is not None:
            profiles = Environment.get_active_profiles()
            if profiles:
                return profiles[0]
        else:
            try:
                from flashboot_core.env import Environment as _Env

                Environment = _Env
                profiles = Environment.get_active_profiles()
                if profiles:
                    return profiles[0]
            except ImportError:
                pass

        return None
