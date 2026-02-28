"""Unit tests for pai_llm_config config singleton and LLMConfig.default()."""

import sys
import threading
import pytest
import yaml
from pathlib import Path
from typing import Any, Dict


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


class TestConfigSingleton:
    """Tests for the config global singleton."""

    def test_lazy_load_and_caching(
        self, temp_config_dir, create_yaml_config, monkeypatch
    ):
        config_content_v1 = {
            "version": "1",
            "providers": {"p1": {"type": "openai", "api_key": "v1_key"}},
            "models": {"m1": {"provider": "p1", "model": "m1_v1"}},
        }
        config_content_v2 = {
            "version": "1",
            "providers": {"p1": {"type": "openai", "api_key": "v2_key"}},
            "models": {"m1": {"provider": "p1", "model": "m1_v2"}},
        }

        create_yaml_config("llm-config.yaml", config_content_v1)
        monkeypatch.chdir(temp_config_dir)

        from pai_llm_config import config

        assert config.get("m1").model == "m1_v1"

        # Modify config file without reloading
        create_yaml_config("llm-config.yaml", config_content_v2)

        # Should still get old config due to caching
        assert config.get("m1").model == "m1_v1"

        # Force reload
        config.reload()
        assert config.get("m1").model == "m1_v2"

    def test_configure_manual(
        self, temp_config_dir, create_yaml_config, monkeypatch
    ):
        config_content = {
            "version": "1",
            "providers": {"p1": {"type": "openai"}},
            "models": {"m1": {"provider": "p1", "model": "m1_manual"}},
        }
        create_yaml_config("llm-config.yaml", config_content)
        monkeypatch.chdir(temp_config_dir)

        from pai_llm_config import config as cfg
        from pai_llm_config import LLMConfig

        # Manually inject config
        manual_config_instance = LLMConfig(
            {
                "version": "1",
                "providers": {"p_manual": {"type": "openai"}},
                "models": {"m_manual": {"provider": "p_manual", "model": "manual_model"}},
            }
        )
        cfg.configure(manual_config_instance)

        assert cfg.get("m_manual").model == "manual_model"

        # Auto-discovered config should not override manually configured one unless reloaded
        assert cfg.get("m_manual").model == "manual_model"

        cfg.reload()
        assert cfg.get("m1").model == "m1_manual"


class TestLLMConfigDefault:
    """Tests for LLMConfig.default() class-level singleton."""

    @pytest.fixture(autouse=True)
    def reset_singleton(self):
        """Ensure clean state before and after each test."""
        from pai_llm_config import LLMConfig
        LLMConfig.reset_default()
        yield
        LLMConfig.reset_default()

    def test_default_returns_llmconfig(
        self, temp_config_dir, create_yaml_config, monkeypatch
    ):
        create_yaml_config(
            "llm-config.yaml",
            {
                "version": "1",
                "providers": {"p1": {"type": "openai", "api_key": "sk-test"}},
                "models": {"m1": {"provider": "p1", "model": "gpt-4o"}},
            },
        )
        monkeypatch.chdir(temp_config_dir)

        from pai_llm_config import LLMConfig
        cfg = LLMConfig.default()
        assert isinstance(cfg, LLMConfig)
        assert cfg.get("m1").model == "gpt-4o"

    def test_default_returns_same_instance(
        self, temp_config_dir, create_yaml_config, monkeypatch
    ):
        create_yaml_config(
            "llm-config.yaml",
            {
                "version": "1",
                "providers": {"p1": {"type": "openai"}},
                "models": {"m1": {"provider": "p1", "model": "gpt-4o"}},
            },
        )
        monkeypatch.chdir(temp_config_dir)

        from pai_llm_config import LLMConfig
        config1 = LLMConfig.default()
        config2 = LLMConfig.default()
        assert config1 is config2

    def test_default_is_thread_safe(
        self, temp_config_dir, create_yaml_config, monkeypatch
    ):
        create_yaml_config(
            "llm-config.yaml",
            {
                "version": "1",
                "providers": {"p1": {"type": "openai"}},
                "models": {"m1": {"provider": "p1", "model": "gpt-4o"}},
            },
        )
        monkeypatch.chdir(temp_config_dir)

        from pai_llm_config import LLMConfig
        results = []

        def get_default():
            results.append(LLMConfig.default())

        threads = [threading.Thread(target=get_default) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert len(results) == 10
        assert all(r is results[0] for r in results)

    def test_reset_default_clears_singleton(
        self, temp_config_dir, create_yaml_config, monkeypatch
    ):
        create_yaml_config(
            "llm-config.yaml",
            {
                "version": "1",
                "providers": {"p1": {"type": "openai", "api_key": "key-v1"}},
                "models": {"m1": {"provider": "p1", "model": "gpt-4o"}},
            },
        )
        monkeypatch.chdir(temp_config_dir)

        from pai_llm_config import LLMConfig
        config1 = LLMConfig.default()

        # Update config and reset
        create_yaml_config(
            "llm-config.yaml",
            {
                "version": "1",
                "providers": {"p1": {"type": "openai", "api_key": "key-v2"}},
                "models": {"m1": {"provider": "p1", "model": "gpt-4o-mini"}},
            },
        )
        LLMConfig.reset_default()
        config2 = LLMConfig.default()

        assert config1 is not config2
        assert config2.get("m1").model == "gpt-4o-mini"

    def test_default_used_by_config_singleton(
        self, temp_config_dir, create_yaml_config, monkeypatch
    ):
        """config singleton delegates to LLMConfig.default()."""
        create_yaml_config(
            "llm-config.yaml",
            {
                "version": "1",
                "providers": {"p1": {"type": "openai"}},
                "models": {"m1": {"provider": "p1", "model": "gpt-4o"}},
            },
        )
        monkeypatch.chdir(temp_config_dir)

        from pai_llm_config import LLMConfig, config as cfg
        # Reset singleton internal state
        cfg._config = None

        config_via_default = LLMConfig.default()
        config_via_singleton = cfg._get_config()
        assert config_via_default is config_via_singleton
