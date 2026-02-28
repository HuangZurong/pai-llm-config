import os
import yaml
import tomli
import copy
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from dotenv import load_dotenv

# Assuming LLMConfigSchema and other models are defined in pai_llm_config.models
# from .models import LLMConfigSchema


class ConfigLoaderError(Exception):
    """Custom exception for configuration loading errors."""

    pass


class ConfigLoader:
    """Handles loading and merging of configuration from multiple sources."""

    def __init__(self, root_path: Optional[Path] = None):
        self._root_path = root_path

    def load_config_data(
        self,
        profile: Optional[str] = None,
        config_path: Optional[Union[str, Path]] = None,
        dotenv_path: Optional[Union[str, Path]] = None,
        load_dotenv_file: bool = True,
    ) -> Dict[str, Any]:
        """
        Loads configuration data from various sources and merges them.

        Priority (low to high):
        1. Default config (empty or from base config file)
        2. Config file (YAML/TOML) specified by config_path or auto-discovered
        3. Profile overrides (e.g., development, production)
        4. .env file variables
        5. OS environment variables
        """
        base_config: Dict[str, Any] = {}

        # 1. Load base configuration
        if config_path:
            base_config = self._load_file(config_path)
        else:
            base_config = self._auto_discover_config_file()

        # 2. Load profile-specific configuration file (if profile is provided)
        # This follows the "Addition instead of Modification" principle
        if profile:
            profile_file_config = self._auto_discover_config_file(profile=profile)
            if profile_file_config:
                base_config = self._deep_merge_dicts(base_config, profile_file_config)

        # 3. Load .env file
        if load_dotenv_file:
            if dotenv_path:
                load_dotenv(dotenv_path=dotenv_path, override=True)
            else:
                # Auto-discover .env in root_path or cwd
                self._auto_discover_dotenv()

        # 4. Apply profile-specific overrides
        if profile and "profiles" in base_config:
            resolved = self._resolve_profile(profile, base_config["profiles"])
            if resolved and resolved in base_config["profiles"]:
                profile_override = base_config["profiles"].pop(resolved)
                base_config = self._deep_merge_dicts(base_config, profile_override)

        # Remove profiles section after applying, it's not part of final config schema
        if "profiles" in base_config:
            del base_config["profiles"]

        return base_config

    def _load_file(self, file_path: Union[str, Path]) -> Dict[str, Any]:
        path = Path(file_path)
        if not path.is_file():
            raise ConfigLoaderError(f"Config file not found: {file_path}")

        try:
            content = path.read_text(encoding="utf-8")
            if path.suffix in (".yaml", ".yml"):
                data = yaml.safe_load(content)
            elif path.suffix == ".toml":
                data = tomli.loads(content)
            else:
                raise ConfigLoaderError(
                    f"Unsupported config file format: {path.suffix}"
                )

            return data if data is not None else {}
        except (yaml.YAMLError, tomli.TOMLDecodeError) as e:
            raise ConfigLoaderError(
                f"Error parsing {path.suffix[1:].upper()} file {path}: {e}"
            ) from e
        except Exception as e:
            raise ConfigLoaderError(f"Error reading config file {path}: {e}") from e

    def _auto_discover_config_file(
        self, profile: Optional[str] = None
    ) -> Dict[str, Any]:
        """Auto-discover configuration file in common locations."""
        search_paths: List[Path] = []
        current_dir = Path.cwd()

        # Determine the base filename (llm-config or llm-config-prod)
        base_name = f"llm-config-{profile}" if profile else "llm-config"

        if self._root_path and self._root_path.resolve() != current_dir.resolve():
            search_paths.extend(
                [
                    self._root_path / f"{base_name}.yaml",
                    self._root_path / f"{base_name}.yml",
                    self._root_path / "config" / f"{base_name}.yaml",
                    self._root_path / "config" / f"{base_name}.yml",
                    self._root_path / "resources" / f"{base_name}.yaml",
                    self._root_path / "resources" / f"{base_name}.yml",
                    self._root_path / f".{base_name}.yaml",
                    self._root_path / f".{base_name}.yml",
                    self._root_path / f"{base_name}.toml",
                    self._root_path / "config" / f"{base_name}.toml",
                ]
            )

        # Always search in current working directory
        search_paths.extend(
            [
                current_dir / f"{base_name}.yaml",
                current_dir / f"{base_name}.yml",
                current_dir / "config" / f"{base_name}.yaml",
                current_dir / "config" / f"{base_name}.yml",
                current_dir / "resources" / f"{base_name}.yaml",
                current_dir / "resources" / f"{base_name}.yml",
                current_dir / f".{base_name}.yaml",
                current_dir / f".{base_name}.yml",
                current_dir / f"{base_name}.toml",
                current_dir / "config" / f"{base_name}.toml",
            ]
        )

        # Remove duplicates while preserving order
        seen = set()
        unique_search_paths = []
        for p in search_paths:
            if p not in seen:
                unique_search_paths.append(p)
                seen.add(p)

        for path in unique_search_paths:
            if path.is_file():
                return self._load_file(path)
        return {}

    # Bidirectional mapping: short ↔ full profile names
    PROFILE_ALIASES = {
        "prod": "production",
        "production": "production",
        "dev": "development",
        "development": "development",
        "test": "testing",
        "testing": "testing",
        "stg": "staging",
        "staging": "staging",
        "local": "local",
    }

    def _resolve_profile(self, profile: str, profiles: Dict[str, Any]) -> Optional[str]:
        """Resolve profile name, supporting both short (prod/dev/test) and full names.

        Resolution order:
        1. Exact match in profiles dict
        2. Expand short name → full name, check if full name exists
        3. Contract full name → short name, check if short name exists
        """
        # 1. Exact match
        if profile in profiles:
            return profile

        # 2. Try expanding alias → full name
        full_name = self.PROFILE_ALIASES.get(profile.lower())
        if full_name and full_name in profiles:
            return full_name

        # 3. Try reverse: find which key in profiles matches via alias
        reverse = {v: k for k, v in self.PROFILE_ALIASES.items() if k != v}
        short_name = reverse.get(profile.lower())
        if short_name and short_name in profiles:
            return short_name

        return None

    def _auto_discover_dotenv(self):
        # Load .env from root_path or cwd
        if self._root_path and (self._root_path / ".env").is_file():
            load_dotenv(dotenv_path=self._root_path / ".env", override=False)
        elif (Path.cwd() / ".env").is_file():
            load_dotenv(dotenv_path=Path.cwd() / ".env", override=False)

    def _deep_merge_dicts(
        self, base: Dict[str, Any], override: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Recursively merges override dict into base dict."""
        merged = copy.deepcopy(base)
        for key, value in override.items():
            if (
                key in merged
                and isinstance(merged[key], dict)
                and isinstance(value, dict)
            ):
                merged[key] = self._deep_merge_dicts(merged[key], value)
            else:
                merged[key] = copy.deepcopy(value)
        return merged
