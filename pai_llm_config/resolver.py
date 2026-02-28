import os
import re
from typing import Any, Dict


class ConfigResolverError(Exception):
    """Custom exception for configuration resolution errors."""
    pass


class ConfigResolver:
    """Resolves `${VAR}` placeholders in configuration data."""

    VAR_PATTERN = re.compile(r"\$\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

    def resolve(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively resolves variables in a dictionary."""
        return self._resolve_recursive(config_data)

    def _resolve_recursive(self, item: Any) -> Any:
        if isinstance(item, dict):
            return {k: self._resolve_recursive(v) for k, v in item.items()}
        elif isinstance(item, list):
            return [self._resolve_recursive(elem) for elem in item]
        elif isinstance(item, str):
            return self._resolve_string(item)
        return item

    def _resolve_string(self, text: str) -> str:
        """Resolves ${VAR} placeholders in a single string.

        Supports nested resolution (a resolved value may itself contain ${...}).
        Raises ConfigResolverError if any variable is not set in the environment.
        """
        def replace_var(match: re.Match) -> str:
            var_name = match.group(1)
            value = os.environ.get(var_name)
            if value is None:
                raise ConfigResolverError(f"Environment variable '{var_name}' not set.")
            return value

        # Loop to support nested expansion: ${A} → "${B}" → "value"
        max_passes = 10
        for _ in range(max_passes):
            new_text = self.VAR_PATTERN.sub(replace_var, text)
            if new_text == text:
                break
            text = new_text
        return text
