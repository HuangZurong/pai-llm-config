"""Unit tests for pai_llm_config.resolver — ConfigResolver."""

import os
import pytest

from pai_llm_config.resolver import ConfigResolver, ConfigResolverError


class TestResolveString:
    """Tests for ConfigResolver._resolve_string()."""

    def test_single_env_var(self):
        os.environ["TEST_RESOLVE_VAR"] = "resolved_value"
        resolver = ConfigResolver()
        result = resolver._resolve_string("This is a ${TEST_RESOLVE_VAR}.")
        assert result == "This is a resolved_value."
        del os.environ["TEST_RESOLVE_VAR"]

    def test_multiple_env_vars(self):
        os.environ["VAR1"] = "VALUE1"
        os.environ["VAR2"] = "VALUE2"
        resolver = ConfigResolver()
        result = resolver._resolve_string("First: ${VAR1}, Second: ${VAR2}")
        assert result == "First: VALUE1, Second: VALUE2"
        del os.environ["VAR1"]
        del os.environ["VAR2"]

    def test_missing_env_var_raises(self):
        resolver = ConfigResolver()
        with pytest.raises(
            ConfigResolverError, match="Environment variable 'NON_EXISTENT_VAR' not set."
        ):
            resolver._resolve_string("Missing: ${NON_EXISTENT_VAR}")


class TestResolveDict:
    """Tests for ConfigResolver.resolve() with nested structures."""

    def test_recursive_dict_and_list(self):
        os.environ["KEY_ENV"] = "env_key"
        os.environ["BASE_URL_ENV"] = "https://api.example.com"
        config_data = {
            "provider": {"api_key": "${KEY_ENV}", "api_base": "${BASE_URL_ENV}"},
            "models": [{"name": "gpt", "description": "Model with key ${KEY_ENV}"}],
        }
        resolver = ConfigResolver()
        resolved_config = resolver.resolve(config_data)
        expected_config = {
            "provider": {"api_key": "env_key", "api_base": "https://api.example.com"},
            "models": [{"name": "gpt", "description": "Model with key env_key"}],
        }
        assert resolved_config == expected_config
        del os.environ["KEY_ENV"]
        del os.environ["BASE_URL_ENV"]
