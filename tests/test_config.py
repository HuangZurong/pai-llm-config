"""Unit tests for pai_llm_config.config — LLMConfig."""

import os
import sys
import pytest
import yaml
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock

from pai_llm_config.models import LLMConfigSchema, ModelConfig, ProviderConfig, AliasConfig
from pai_llm_config.config import (
    LLMConfig,
    ConfigValidationError,
    ModelNotFoundError,
    ProviderNotFoundError,
    AliasConflictError,
    ModelTypeMismatchError,
)


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def temp_config_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def create_yaml_config(temp_config_dir):
    def _creator(filename: str, content: Dict[str, Any]):
        path = temp_config_dir / filename
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(content, f)
        return path

    return _creator


@pytest.fixture
def minimal_valid_config_data():
    return {
        "version": "1",
        "providers": {"openai": {"type": "openai", "api_key": "sk-test"}},
        "models": {"gpt4o": {"provider": "openai", "model": "gpt-4o"}},
    }


@pytest.fixture
def full_valid_config_data():
    return {
        "version": "1",
        "defaults": {"temperature": 0.7},
        "providers": {
            "anthropic": {"type": "anthropic", "api_key": "ant-key"},
            "openai-proxy": {
                "type": "openai",
                "api_base": "https://proxy.com/v1",
                "api_keys": [
                    {"key": "key1", "alias": "k1", "priority": 1},
                    {"key": "key2", "alias": "k2", "priority": 2},
                ],
                "key_strategy": "priority",
            },
        },
        "models": {
            "gpt4o": {
                "provider": "openai-proxy",
                "model": "gpt-4o",
                "temperature": 0.3,
            },
            "claude": {
                "provider": "anthropic",
                "model": "claude-sonnet",
                "type": "chat",
            },
            "embedding-model": {
                "provider": "openai-proxy",
                "model": "text-embedding",
                "type": "embedding",
            },
        },
        "aliases": {"smart": "gpt4o", "chat_claude": "claude"},
        "fallbacks": {"smart": ["gpt4o", "claude"]},
        "routing": {
            "presets": {"code_gen": "smart"},
            "rules": [
                {"when": {"max_tokens_gt": 4000}, "use": "gpt4o"},
                {"default": "claude"},
            ],
        },
        "environments": {
            "dev": {
                "defaults": {"temperature": 0.9},
                "providers": {
                    "openai-proxy": {
                        "type": "openai",
                        "api_base": "http://dev-proxy.com",
                    }
                },
                "aliases": {"smart": "claude"},
            }
        },
    }


# ============================================================
# Pydantic validation
# ============================================================


class TestPydanticValidation:
    """Tests for Pydantic schema validation."""

    def test_success(self, minimal_valid_config_data):
        config = LLMConfig(minimal_valid_config_data)
        assert config._config_schema.version == "1"
        assert "openai" in config._providers

    def test_invalid_version_type(self):
        invalid_config = {"version": 1.0}  # Version should be string
        with pytest.raises(ConfigValidationError, match="Pydantic validation error"):
            LLMConfig(invalid_config)


# ============================================================
# Semantic validation
# ============================================================


class TestSemanticValidation:
    """Tests for post-Pydantic semantic validation."""

    def test_provider_not_found(self):
        invalid_config = {
            "version": "1",
            "providers": {},
            "models": {"gpt": {"provider": "nonexistent", "model": "gpt-3.5"}},
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            LLMConfig(invalid_config)
        assert "references non-existent provider 'nonexistent'" in str(exc_info.value)

    def test_model_not_found_in_alias(self):
        invalid_config = {
            "version": "1",
            "providers": {"p1": {"type": "openai"}},
            "models": {},
            "aliases": {"smart": "nonexistent_model"},
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            LLMConfig(invalid_config)
        assert "Alias 'smart' references non-existent model 'nonexistent_model'" in str(
            exc_info.value
        )

    def test_alias_conflict(self):
        invalid_config = {
            "version": "1",
            "providers": {"p1": {"type": "openai"}},
            "models": {"gpt4o": {"provider": "p1", "model": "gpt-4o"}},
            "aliases": {"gpt4o": "gpt4o"},
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            LLMConfig(invalid_config)
        assert "Alias 'gpt4o' conflicts with an existing model name" in str(exc_info.value)

    def test_chat_alias_to_embedding_model(self):
        invalid_config = {
            "version": "1",
            "providers": {"p1": {"type": "openai"}},
            "models": {
                "text-embed": {
                    "provider": "p1",
                    "model": "embedding-v1",
                    "type": "embedding",
                }
            },
            "aliases": {"smart_embedding": "text-embed", "chat_alias": "text-embed"},
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            LLMConfig(invalid_config)
        assert "Chat alias 'chat_alias' points to an embedding model 'text-embed'" in str(
            exc_info.value
        )

    def test_fallback_model_not_found(self):
        invalid_config = {
            "version": "1",
            "providers": {"p1": {"type": "openai"}},
            "models": {"m1": {"provider": "p1", "model": "m1"}},
            "fallbacks": {"f1": ["m1", "nonexistent"]},
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            LLMConfig(invalid_config)
        assert (
            "Fallback 'f1' at index 1 references non-existent model 'nonexistent'"
            in str(exc_info.value)
        )

    def test_routing_rule_model_not_found(self):
        invalid_config = {
            "version": "1",
            "providers": {"p1": {"type": "openai"}},
            "models": {"m1": {"provider": "p1", "model": "m1"}},
            "routing": {"rules": [{"when": {"max_tokens_gt": 100}, "use": "nonexistent"}]},
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            LLMConfig(invalid_config)
        assert "Routing rule 0 references non-existent model or alias 'nonexistent'" in str(
            exc_info.value
        )

    def test_routing_rule_default_model_not_found(self):
        invalid_config = {
            "version": "1",
            "providers": {"p1": {"type": "openai"}},
            "models": {"m1": {"provider": "p1", "model": "m1"}},
            "routing": {"rules": [{"default": "nonexistent_default"}]},
        }
        with pytest.raises(ConfigValidationError) as exc_info:
            LLMConfig(invalid_config)
        assert (
            "Routing rule 0 default references non-existent model or alias 'nonexistent_default'"
            in str(exc_info.value)
        )

    def test_full_valid_config_passes(self, full_valid_config_data):
        LLMConfig(full_valid_config_data)  # Should not raise


# ============================================================
# LLMConfig.load()
# ============================================================


class TestLoad:
    """Tests for LLMConfig.load() integration."""

    def test_auto_discovery(self, create_yaml_config, temp_config_dir, monkeypatch):
        config_content = {
            "version": "1",
            "providers": {"p1": {"type": "openai"}},
            "models": {"m1": {"provider": "p1", "model": "m1"}},
        }
        create_yaml_config("llm-config.yaml", config_content)
        monkeypatch.chdir(temp_config_dir)

        config = LLMConfig.load()
        assert config.get("m1").model == "m1"

    def test_explicit_config_path(self, create_yaml_config, minimal_valid_config_data):
        config_path = create_yaml_config("my-config.yaml", minimal_valid_config_data)
        config = LLMConfig.load(config_path=config_path)
        assert config.get("gpt4o").model == "gpt-4o"

    def test_profile_override(self, create_yaml_config, temp_config_dir, monkeypatch):
        config_content = {
            "version": "1",
            "providers": {"p1": {"type": "openai", "api_key": "base_key"}},
            "models": {"m1": {"provider": "p1", "model": "m1", "temperature": 0.7}},
            "profiles": {
                "dev": {
                    "providers": {"p1": {"type": "openai", "api_key": "dev_key"}},
                    "models": {"m1": {"temperature": 0.9}},
                }
            },
        }
        create_yaml_config("llm-config.yaml", config_content)
        monkeypatch.chdir(temp_config_dir)
        monkeypatch.setenv("LLM_CONFIG_PROFILE", "dev")

        config = LLMConfig.load()
        assert config._config_schema.providers["p1"].api_key == "dev_key"
        assert config._config_schema.models["m1"].temperature == 0.9

    def test_dotenv_and_env_vars(
        self, temp_config_dir, create_yaml_config, monkeypatch
    ):
        # Create .env file
        dotenv_path = temp_config_dir / ".env"
        dotenv_path.write_text("DOTENV_KEY=dotenv_secret\nOVERRIDE_ME=dotenv_override\n")

        config_content = {
            "version": "1",
            "providers": {"p1": {"type": "openai", "api_key": "${DOTENV_KEY}"}},
            "models": {"m1": {"provider": "p1", "model": "gpt-3.5"}},
        }
        create_yaml_config("llm-config.yaml", config_content)

        monkeypatch.chdir(temp_config_dir)
        monkeypatch.setenv("OVERRIDE_ME", "os_env_override")

        config = LLMConfig.load(dotenv=True)
        assert config._config_schema.providers["p1"].api_key == "dotenv_secret"
        assert os.environ.get("OVERRIDE_ME") == "os_env_override"

        del os.environ["DOTENV_KEY"]
        del os.environ["OVERRIDE_ME"]

    def test_flashboot_core_root_path(
        self, create_yaml_config, temp_config_dir, monkeypatch
    ):
        from pai_llm_config.config import LLMConfig as _  # noqa: F401 ensure module loaded
        config_module = sys.modules["pai_llm_config.config"]
        mock_project_utils = MagicMock()
        mock_project_utils.get_root_path.return_value = str(temp_config_dir)
        monkeypatch.setattr(config_module, "project_utils", mock_project_utils)

        config_content = {
            "version": "1",
            "providers": {"p1": {"type": "openai"}},
            "models": {"m1": {"provider": "p1", "model": "m1"}},
        }
        create_yaml_config("llm-config.yaml", config_content)

        other_dir = temp_config_dir / "other"
        other_dir.mkdir()
        monkeypatch.chdir(other_dir)

        config = LLMConfig.load()
        assert config.get("m1").model == "m1"

    def test_flashboot_core_profile(
        self, create_yaml_config, temp_config_dir, monkeypatch
    ):
        config_module = sys.modules["pai_llm_config.config"]
        mock_environment = MagicMock()
        mock_environment.get_active_profiles.return_value = ["dev"]
        monkeypatch.setattr(config_module, "Environment", mock_environment)

        config_content = {
            "version": "1",
            "providers": {"p1": {"type": "openai", "api_key": "base_key"}},
            "models": {"m1": {"provider": "p1", "model": "m1", "temperature": 0.7}},
            "profiles": {
                "dev": {"providers": {"p1": {"api_key": "dev_key"}}},
            },
        }
        create_yaml_config("llm-config.yaml", config_content)
        monkeypatch.chdir(temp_config_dir)

        config = LLMConfig.load()
        assert config._config_schema.providers["p1"].api_key == "dev_key"


# ============================================================
# LLMConfig.get()
# ============================================================


class TestGet:
    """Tests for LLMConfig.get() model resolution."""

    def test_by_name(self, minimal_valid_config_data):
        config = LLMConfig(minimal_valid_config_data)
        model = config.get("gpt4o")
        assert model.model == "gpt-4o"
        assert model.provider == "openai"

    def test_by_alias(self, full_valid_config_data):
        config = LLMConfig(full_valid_config_data)
        model = config.get("smart")
        assert model.model == "gpt-4o"
        assert model.provider == "openai-proxy"

    def test_not_found(self, minimal_valid_config_data):
        config = LLMConfig(minimal_valid_config_data)
        with pytest.raises(
            ModelNotFoundError, match="Model or alias 'nonexistent' not found"
        ):
            config.get("nonexistent")

    def test_merged_defaults(self, full_valid_config_data):
        config = LLMConfig(full_valid_config_data)
        gpt4o_model = config.get("gpt4o")
        assert gpt4o_model.temperature == 0.3  # Model level overrides global

        claude_model = config.get("claude")
        assert claude_model.temperature == 0.7  # Inherits from global defaults
