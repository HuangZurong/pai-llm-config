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

def test_model_aliases_in_params():
    """Test that model_id and model_name are included in output params."""
    config_data = {
        "version": "1",
        "providers": {"openai": {"type": "openai", "api_key": "sk-test"}},
        "models": {"gpt4": {"provider": "openai", "model": "gpt-4o"}},
    }
    config = LLMConfig(config_data)

    # Test to_params (L1 standard)
    params = config.to_params("gpt4")
    assert params["model"] == "gpt-4o"
    assert params["model_id"] == "gpt-4o"
    assert params["model_name"] == "gpt-4o"

    # Test to_litellm_params
    litellm_params = config.to_litellm_params("gpt4")
    assert litellm_params["model"] == "openai/gpt-4o"
    assert litellm_params["model_id"] == "openai/gpt-4o"
    assert litellm_params["model_name"] == "openai/gpt-4o"

    # Test to_dspy_params
    dspy_params = config.to_dspy_params("gpt4")
    assert dspy_params["model"] == "openai/gpt-4o"
    assert dspy_params["model_id"] == "openai/gpt-4o"
    assert dspy_params["model_name"] == "openai/gpt-4o"

