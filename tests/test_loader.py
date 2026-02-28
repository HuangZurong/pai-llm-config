"""Unit tests for pai_llm_config.loader — ConfigLoader."""

import os
import pytest
from pathlib import Path
from unittest.mock import patch

from pai_llm_config.loader import ConfigLoader, ConfigLoaderError


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def tmp_project(tmp_path):
    """Create a temporary project directory with config files."""
    return tmp_path


@pytest.fixture
def yaml_config_content():
    return """\
version: "1"

defaults:
  temperature: 0.7
  max_tokens: 2048

providers:
  openai:
    type: openai
    api_key: ${OPENAI_API_KEY}
    api_base: https://api.openai.com/v1

models:
  gpt4o:
    provider: openai
    model: gpt-4o
    temperature: 0.3

aliases:
  smart: gpt4o

profiles:
  production:
    defaults:
      temperature: 0.1
    providers:
      openai:
        api_base: https://prod-proxy.com/v1
  development:
    defaults:
      temperature: 0.9
"""


@pytest.fixture
def toml_config_content():
    return """\
version = "1"

[defaults]
temperature = 0.5

[providers.openai]
type = "openai"
api_key = "sk-test-key"

[models.gpt4o]
provider = "openai"
model = "gpt-4o"
"""


@pytest.fixture
def yaml_config_file(tmp_project, yaml_config_content):
    """Create a YAML config file in the temp project."""
    config_file = tmp_project / "llm-config.yaml"
    config_file.write_text(yaml_config_content, encoding="utf-8")
    return config_file


@pytest.fixture
def toml_config_file(tmp_project, toml_config_content):
    """Create a TOML config file in the temp project."""
    config_file = tmp_project / "llm-config.toml"
    config_file.write_text(toml_config_content, encoding="utf-8")
    return config_file


@pytest.fixture
def dotenv_file(tmp_project):
    """Create a .env file in the temp project."""
    env_file = tmp_project / ".env"
    env_file.write_text(
        "OPENAI_API_KEY=sk-from-dotenv\n" "CUSTOM_VAR=hello-from-dotenv\n",
        encoding="utf-8",
    )
    return env_file


# ============================================================
# _load_file 测试
# ============================================================


class TestLoadFile:
    """Tests for ConfigLoader._load_file()."""

    def test_load_yaml(self, yaml_config_file):
        loader = ConfigLoader()
        data = loader._load_file(yaml_config_file)

        assert data["version"] == "1"
        assert data["defaults"]["temperature"] == 0.7
        assert data["providers"]["openai"]["type"] == "openai"
        assert data["models"]["gpt4o"]["model"] == "gpt-4o"
        assert data["aliases"]["smart"] == "gpt4o"

    def test_load_toml(self, toml_config_file):
        loader = ConfigLoader()
        data = loader._load_file(toml_config_file)

        assert data["version"] == "1"
        assert data["defaults"]["temperature"] == 0.5
        assert data["providers"]["openai"]["type"] == "openai"
        assert data["models"]["gpt4o"]["model"] == "gpt-4o"

    def test_load_yml_extension(self, tmp_project):
        yml_file = tmp_project / "config.yml"
        yml_file.write_text('version: "1"\ndefaults:\n  temperature: 0.8\n')
        loader = ConfigLoader()
        data = loader._load_file(yml_file)
        assert data["version"] == "1"
        assert data["defaults"]["temperature"] == 0.8

    def test_file_not_found(self):
        loader = ConfigLoader()
        with pytest.raises(ConfigLoaderError, match="Config file not found"):
            loader._load_file("/nonexistent/path/config.yaml")

    def test_unsupported_format(self, tmp_project):
        json_file = tmp_project / "config.json"
        json_file.write_text('{"version": "1"}')
        loader = ConfigLoader()
        with pytest.raises(ConfigLoaderError, match="Unsupported config file format"):
            loader._load_file(json_file)

    def test_load_empty_file(self, tmp_project):
        """Empty YAML file should return empty dict instead of None."""
        empty_file = tmp_project / "empty.yaml"
        empty_file.write_text("", encoding="utf-8")
        loader = ConfigLoader()
        assert loader._load_file(empty_file) == {}

    def test_load_malformed_file(self, tmp_project):
        """Malformed YAML file should raise ConfigLoaderError."""
        bad_file = tmp_project / "bad.yaml"
        bad_file.write_text("invalid: [unclosed bracket", encoding="utf-8")
        loader = ConfigLoader()
        with pytest.raises(ConfigLoaderError, match="Error parsing YAML file"):
            loader._load_file(bad_file)


# ============================================================
# _auto_discover_config_file 测试
# ============================================================


class TestAutoDiscoverConfigFile:
    """Tests for ConfigLoader._auto_discover_config_file()."""

    def test_discover_in_root(self, tmp_project, yaml_config_content):
        (tmp_project / "llm-config.yaml").write_text(yaml_config_content)
        loader = ConfigLoader(root_path=tmp_project)
        data = loader._auto_discover_config_file()
        assert data["version"] == "1"

    def test_discover_yml_extension(self, tmp_project, yaml_config_content):
        (tmp_project / "llm-config.yml").write_text(yaml_config_content)
        loader = ConfigLoader(root_path=tmp_project)
        data = loader._auto_discover_config_file()
        assert data["version"] == "1"

    def test_discover_in_config_subdir(self, tmp_project, yaml_config_content):
        config_dir = tmp_project / "config"
        config_dir.mkdir()
        (config_dir / "llm-config.yaml").write_text(yaml_config_content)
        loader = ConfigLoader(root_path=tmp_project)
        data = loader._auto_discover_config_file()
        assert data["version"] == "1"

    def test_discover_in_resources_subdir(self, tmp_project, yaml_config_content):
        res_dir = tmp_project / "resources"
        res_dir.mkdir()
        (res_dir / "llm-config.yaml").write_text(yaml_config_content)
        loader = ConfigLoader(root_path=tmp_project)
        data = loader._auto_discover_config_file()
        assert data["version"] == "1"

    def test_discover_hidden_file(self, tmp_project, yaml_config_content):
        (tmp_project / ".llm-config.yaml").write_text(yaml_config_content)
        loader = ConfigLoader(root_path=tmp_project)
        data = loader._auto_discover_config_file()
        assert data["version"] == "1"

    def test_yaml_priority_over_yml(self, tmp_project):
        """llm-config.yaml should be found before llm-config.yml."""
        (tmp_project / "llm-config.yaml").write_text('version: "yaml"\n')
        (tmp_project / "llm-config.yml").write_text('version: "yml"\n')
        loader = ConfigLoader(root_path=tmp_project)
        data = loader._auto_discover_config_file()
        assert data["version"] == "yaml"

    def test_no_config_returns_empty(self, tmp_project):
        loader = ConfigLoader(root_path=tmp_project)
        # Use a fresh tmp project or make sure it's empty
        with patch("pai_llm_config.loader.Path.cwd", return_value=tmp_project):
            data = loader._auto_discover_config_file()
        assert data == {}


class TestAutoDiscoverProfileFile:
    """Tests for discovering profile-specific configuration files."""

    def test_discover_profile_file(self, tmp_project):
        # Base config
        (tmp_project / "llm-config.yaml").write_text(
            "version: '1'\ndefaults:\n  temp: 0.7"
        )
        # Profile config
        (tmp_project / "llm-config-prod.yaml").write_text("defaults:\n  temp: 0.1")

        loader = ConfigLoader(root_path=tmp_project)
        # Load with profile
        data = loader.load_config_data(profile="prod", load_dotenv_file=False)

        assert data["version"] == "1"
        assert data["defaults"]["temp"] == 0.1

    def test_profile_file_priority_over_base(self, tmp_project):
        """Profile file should override base file values."""
        (tmp_project / "llm-config.yaml").write_text("version: '1'\nkey: base")
        (tmp_project / "llm-config-dev.yaml").write_text("key: dev")

        loader = ConfigLoader(root_path=tmp_project)
        data = loader.load_config_data(profile="dev", load_dotenv_file=False)
        assert data["key"] == "dev"

    def test_profile_section_priority_over_profile_file(self, tmp_project):
        """The 'profiles' section (in either file) should have the final say."""
        base_content = """
version: "1"
key: base
profiles:
  prod:
    key: section-priority
"""
        (tmp_project / "llm-config.yaml").write_text(base_content)
        # Profile file also has 'key'
        (tmp_project / "llm-config-prod.yaml").write_text("key: file-priority")

        loader = ConfigLoader(root_path=tmp_project)
        data = loader.load_config_data(profile="prod", load_dotenv_file=False)

        # Order:
        # 1. Base (key: base)
        # 2. Profile File (key: file-priority) -> merged into base
        # 3. Profile Section (key: section-priority) -> final override
        assert data["key"] == "section-priority"


# ============================================================
# _auto_discover_dotenv 测试
# ============================================================


class TestConfigAliases:
    """Tests for field aliases like base_url, temp, etc."""

    def test_provider_and_model_aliases(self, tmp_project):
        config_content = """
version: "1"
defaults:
  temp: 0.1 # Alias for temperature
  max-tokens: 100 # Alias for max_tokens
providers:
  openai:
    type: openai
    base_url: https://alias-test.com/v1 # Alias for api_base
models:
  gpt4o:
    provider: openai
    model: gpt-4o
    temp: 0.2
"""
        config_file = tmp_project / "alias-config.yaml"
        config_file.write_text(config_content)

        loader = ConfigLoader()
        data = loader.load_config_data(config_path=config_file, load_dotenv_file=False)

        # Test loader doesn't transform keys, Pydantic does
        from pai_llm_config.config import LLMConfig

        config = LLMConfig(data)

        # Check provider alias
        assert (
            str(config._providers["openai"].api_base).rstrip("/")
            == "https://alias-test.com/v1"
        )
        # Check defaults alias
        assert config._config_schema.defaults.temperature == 0.1
        # Check model override alias
        assert config._models["gpt4o"].temperature == 0.2
        assert config._models["gpt4o"].max_tokens is None  # max-tokens was in defaults


class TestModelMappings:
    """Tests for the Model Mappings feature."""

    def test_basic_mapping(self, tmp_project):
        config_content = """
version: "1"
providers:
  deepseek:
    type: openai
    api_key: sk-ds
    api_base: https://api.deepseek.com/v1
models:
  ds-chat:
    provider: deepseek
    model: deepseek-chat
mappings:
  "openai/gpt-4": "ds-chat"
  "gpt-4": "ds-chat"
"""
        config_file = tmp_project / "mapping-config.yaml"
        config_file.write_text(config_content)

        from pai_llm_config.config import LLMConfig

        loader = ConfigLoader()
        data = loader.load_config_data(config_path=config_file, load_dotenv_file=False)
        config = LLMConfig(data)

        # 1. Test exact mapping (provider/model)
        m1 = config.get("openai/gpt-4")
        assert m1.model == "deepseek-chat"
        assert m1.provider == "deepseek"

        # 2. Test simple name mapping
        m2 = config.get("gpt-4")
        assert m2.model == "deepseek-chat"

    def test_mapping_to_alias(self, tmp_project):
        """Mappings can point to aliases."""
        config_content = """
version: "1"
providers:
  p1: {type: openai, api_key: k1}
models:
  m1: {provider: p1, model: model-1}
aliases:
  my-alias: m1
mappings:
  "external-name": "my-alias"
"""
        config_file = tmp_project / "map-alias.yaml"
        config_file.write_text(config_content)

        from pai_llm_config.config import LLMConfig

        loader = ConfigLoader()
        data = loader.load_config_data(config_path=config_file, load_dotenv_file=False)
        config = LLMConfig(data)

        m = config.get("external-name")
        assert m.model == "model-1"

    def test_profile_mapping_override(self, tmp_project):
        """Mappings can be overridden or added via profiles."""
        config_content = """
version: "1"
providers:
  p1: {type: openai, api_key: k1}
models:
  m1: {provider: p1, model: model-1}
mappings:
  "gpt-4": "m1"
profiles:
  prod:
    mappings:
      "gpt-4": "prod-model"
    models:
      prod-model: {provider: p1, model: model-prod}
"""
        config_file = tmp_project / "map-profile.yaml"
        config_file.write_text(config_content)

        from pai_llm_config.config import LLMConfig

        loader = ConfigLoader()

        # Base check
        data_base = loader.load_config_data(
            config_path=config_file, load_dotenv_file=False
        )
        assert LLMConfig(data_base).get("gpt-4").model == "model-1"

        # Profile check
        data_prod = loader.load_config_data(
            config_path=config_file, profile="prod", load_dotenv_file=False
        )
        assert LLMConfig(data_prod).get("gpt-4").model == "model-prod"

    def test_protocol_metadata(self, tmp_project):
        """Protocol metadata is optional and correctly loaded."""
        config_content = """
version: "1"
providers:
  p1: {type: openai, api_key: k1}
models:
  m1: 
    provider: p1
    model: mod-1
    protocol: openai-v1
  m2:
    provider: p1
    model: mod-2
    # protocol is omitted
"""
        config_file = tmp_project / "protocol.yaml"
        config_file.write_text(config_content)

        from pai_llm_config.config import LLMConfig

        loader = ConfigLoader()
        data = loader.load_config_data(config_path=config_file, load_dotenv_file=False)
        config = LLMConfig(data)

        assert config.get("m1").protocol == "openai-v1"
        assert config.get("m2").protocol is None

    def test_dotenv_loaded_from_root(self, tmp_project, dotenv_file):
        loader = ConfigLoader(root_path=tmp_project)
        # Clear any existing value
        os.environ.pop("CUSTOM_VAR", None)
        loader._auto_discover_dotenv()
        # .env should have been loaded
        assert os.environ.get("CUSTOM_VAR") == "hello-from-dotenv"
        # Cleanup
        os.environ.pop("CUSTOM_VAR", None)

    def test_dotenv_does_not_override_os_env(self, tmp_project, dotenv_file):
        """OS environment variables should NOT be overridden by .env."""
        os.environ["CUSTOM_VAR"] = "from-os"
        loader = ConfigLoader(root_path=tmp_project)
        loader._auto_discover_dotenv()
        assert os.environ["CUSTOM_VAR"] == "from-os"
        # Cleanup
        os.environ.pop("CUSTOM_VAR", None)

    def test_no_dotenv_is_ok(self, tmp_project):
        """No .env file should not raise."""
        loader = ConfigLoader(root_path=tmp_project)
        loader._auto_discover_dotenv()  # Should not raise


# ============================================================
# _deep_merge_dicts 测试
# ============================================================


class TestDeepMergeDicts:
    """Tests for ConfigLoader._deep_merge_dicts()."""

    def test_simple_merge(self):
        loader = ConfigLoader()
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = loader._deep_merge_dicts(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_nested_merge(self):
        loader = ConfigLoader()
        base = {"defaults": {"temperature": 0.7, "max_tokens": 2048}}
        override = {"defaults": {"temperature": 0.1}}
        result = loader._deep_merge_dicts(base, override)
        assert result == {"defaults": {"temperature": 0.1, "max_tokens": 2048}}

    def test_deeply_nested_merge(self):
        loader = ConfigLoader()
        base = {
            "providers": {
                "openai": {"api_base": "https://old.com", "api_key": "sk-xxx"}
            }
        }
        override = {"providers": {"openai": {"api_base": "https://new.com"}}}
        result = loader._deep_merge_dicts(base, override)
        assert result["providers"]["openai"]["api_base"] == "https://new.com"
        assert result["providers"]["openai"]["api_key"] == "sk-xxx"

    def test_override_replaces_non_dict(self):
        loader = ConfigLoader()
        base = {"a": {"b": 1}}
        override = {"a": "hello"}
        result = loader._deep_merge_dicts(base, override)
        assert result == {"a": "hello"}

    def test_list_is_replaced_not_merged(self):
        loader = ConfigLoader()
        base = {"tags": [1, 2, 3]}
        override = {"tags": [4, 5]}
        result = loader._deep_merge_dicts(base, override)
        assert result == {"tags": [4, 5]}

    def test_base_is_not_mutated(self):
        loader = ConfigLoader()
        base = {"a": 1, "b": 2}
        override = {"b": 99}
        loader._deep_merge_dicts(base, override)
        assert base == {"a": 1, "b": 2}


# ============================================================
# load_config_data 集成测试
# ============================================================


class TestLoadConfigData:
    """Integration tests for ConfigLoader.load_config_data()."""

    def test_load_explicit_path(self, yaml_config_file):
        loader = ConfigLoader()
        data = loader.load_config_data(
            config_path=yaml_config_file, load_dotenv_file=False
        )
        assert data["version"] == "1"
        assert data["models"]["gpt4o"]["model"] == "gpt-4o"
        # profiles section should be removed
        assert "profiles" not in data

    def test_load_with_env_override(self, yaml_config_file):
        loader = ConfigLoader()
        data = loader.load_config_data(
            config_path=yaml_config_file,
            profile="production",
            load_dotenv_file=False,
        )
        # production overrides temperature to 0.1
        assert data["defaults"]["temperature"] == 0.1
        # production overrides api_base
        assert data["providers"]["openai"]["api_base"] == "https://prod-proxy.com/v1"
        # profiles should be removed
        assert "profiles" not in data

    def test_load_with_dev_env(self, yaml_config_file):
        loader = ConfigLoader()
        data = loader.load_config_data(
            config_path=yaml_config_file,
            profile="development",
            load_dotenv_file=False,
        )
        assert data["defaults"]["temperature"] == 0.9

    def test_load_nonexistent_env_no_change(self, yaml_config_file):
        loader = ConfigLoader()
        data = loader.load_config_data(
            config_path=yaml_config_file,
            profile="staging",  # Does not exist
            load_dotenv_file=False,
        )
        # Default temperature unchanged
        assert data["defaults"]["temperature"] == 0.7
        assert "profiles" not in data

    def test_load_with_dotenv(self, tmp_project, yaml_config_file, dotenv_file):
        os.environ.pop("CUSTOM_VAR", None)
        loader = ConfigLoader(root_path=tmp_project)
        data = loader.load_config_data(
            config_path=yaml_config_file,
            dotenv_path=dotenv_file,
        )
        # .env should have loaded CUSTOM_VAR
        assert os.environ.get("CUSTOM_VAR") == "hello-from-dotenv"
        os.environ.pop("CUSTOM_VAR", None)

    def test_load_auto_discover(self, tmp_project, yaml_config_content):
        (tmp_project / "llm-config.yaml").write_text(yaml_config_content)
        loader = ConfigLoader(root_path=tmp_project)
        data = loader.load_config_data(load_dotenv_file=False)
        assert data["version"] == "1"
        assert "profiles" not in data

    def test_load_env_override_preserves_unrelated_fields(self, yaml_config_file):
        """Environment override should NOT remove fields not present in override."""
        loader = ConfigLoader()
        data = loader.load_config_data(
            config_path=yaml_config_file,
            profile="production",
            load_dotenv_file=False,
        )
        # max_tokens was not in the production override, should be preserved
        assert data["defaults"]["max_tokens"] == 2048
        # models section should be preserved
        assert "gpt4o" in data["models"]
        # aliases should be preserved
        assert data["aliases"]["smart"] == "gpt4o"

    def test_load_empty_directory(self, tmp_project):
        """Loading from empty directory (no config file) should return empty dict."""
        loader = ConfigLoader(root_path=tmp_project)
        with patch("pai_llm_config.loader.Path.cwd", return_value=tmp_project):
            data = loader.load_config_data(load_dotenv_file=False)
        assert data == {}

    def test_load_toml_explicit_path(self, toml_config_file):
        loader = ConfigLoader()
        data = loader.load_config_data(
            config_path=toml_config_file, load_dotenv_file=False
        )
        assert data["version"] == "1"
        assert data["defaults"]["temperature"] == 0.5

    def test_load_with_short_env_prod(self, yaml_config_file):
        """Short name 'prod' should resolve to 'production' environment."""
        loader = ConfigLoader()
        data = loader.load_config_data(
            config_path=yaml_config_file,
            profile="prod",
            load_dotenv_file=False,
        )
        assert data["defaults"]["temperature"] == 0.1
        assert data["providers"]["openai"]["api_base"] == "https://prod-proxy.com/v1"

    def test_load_with_short_env_dev(self, yaml_config_file):
        """Short name 'dev' should resolve to 'development' environment."""
        loader = ConfigLoader()
        data = loader.load_config_data(
            config_path=yaml_config_file,
            profile="dev",
            load_dotenv_file=False,
        )
        assert data["defaults"]["temperature"] == 0.9


# ============================================================
# _resolve_profile 测试
# ============================================================


class TestResolveProfile:
    """Tests for ConfigLoader._resolve_profile()."""

    def setup_method(self):
        self.loader = ConfigLoader()

    def test_exact_match(self):
        envs = {"production": {}, "development": {}}
        assert self.loader._resolve_profile("production", envs) == "production"
        assert self.loader._resolve_profile("development", envs) == "development"

    def test_short_to_full_name(self):
        """Short name 'prod' resolves to 'production' when config uses full names."""
        envs = {"production": {}, "development": {}, "staging": {}}
        assert self.loader._resolve_profile("prod", envs) == "production"
        assert self.loader._resolve_profile("dev", envs) == "development"
        assert self.loader._resolve_profile("stg", envs) == "staging"

    def test_full_to_short_name(self):
        """Full name 'production' resolves to 'prod' when config uses short names."""
        envs = {"prod": {}, "dev": {}, "stg": {}}
        assert self.loader._resolve_profile("production", envs) == "prod"
        assert self.loader._resolve_profile("development", envs) == "dev"
        assert self.loader._resolve_profile("staging", envs) == "stg"

    def test_case_insensitive(self):
        """Profile name resolution should be case-insensitive."""
        envs = {"production": {}}
        assert self.loader._resolve_profile("Prod", envs) == "production"
        assert self.loader._resolve_profile("PROD", envs) == "production"

    def test_test_profile(self):
        envs = {"testing": {}}
        assert self.loader._resolve_profile("test", envs) == "testing"

    def test_test_profile_short_key(self):
        envs = {"test": {}}
        assert self.loader._resolve_profile("testing", envs) == "test"

    def test_unknown_profile_returns_none(self):
        envs = {"production": {}}
        assert self.loader._resolve_profile("nonexistent", envs) is None

    def test_custom_profile_exact_match(self):
        """Custom profile names not in alias table still work via exact match."""
        envs = {"canary": {}, "blue-green": {}}
        assert self.loader._resolve_profile("canary", envs) == "canary"
        assert self.loader._resolve_profile("blue-green", envs) == "blue-green"

    def test_local_profile(self):
        envs = {"local": {}}
        assert self.loader._resolve_profile("local", envs) == "local"
