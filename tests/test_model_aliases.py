"""Unit tests for model_id and model_name aliases in ModelConfig."""

import pytest
from pai_llm_config.config import LLMConfig

def test_model_id_alias():
    """Test that model_id in config is correctly parsed as model field."""
    config_data = {
        "version": "1",
        "providers": {"openai": {"type": "openai", "api_key": "sk-test"}},
        "models": {
            "gpt4": {
                "provider": "openai",
                "model_id": "gpt-4o"
            }
        },
    }
    config = LLMConfig(config_data)
    model = config.get("gpt4")
    # Pydantic should have mapped model_id -> model
    assert model.model == "gpt-4o"

def test_model_name_alias():
    """Test that model_name in config is correctly parsed as model field."""
    config_data = {
        "version": "1",
        "providers": {"openai": {"type": "openai", "api_key": "sk-test"}},
        "models": {
            "gpt4": {
                "provider": "openai",
                "model_name": "gpt-4o"
            }
        },
    }
    config = LLMConfig(config_data)
    model = config.get("gpt4")
    assert model.model == "gpt-4o"

def test_model_hyphen_alias():
    """Test that model-id and model-name in config are correctly parsed."""
    config_data = {
        "version": "1",
        "providers": {"openai": {"type": "openai", "api_key": "sk-test"}},
        "models": {
            "m1": {"provider": "openai", "model-id": "id1"},
            "m2": {"provider": "openai", "model-name": "name2"},
        },
    }
    config = LLMConfig(config_data)
    assert config.get("m1").model == "id1"
    assert config.get("m2").model == "name2"
