"""KeyPool: manages multiple API keys for a provider with strategy-based selection."""

import threading
from typing import Dict, List, Optional

from ..models import ProviderConfig, KeyConfig
from .strategies import KeyEntry, KeyStrategy, get_strategy


class KeyPoolExhaustedError(Exception):
    """Raised when no keys are available in the pool."""

    pass


class KeyPool:
    """Manages a pool of API keys for a single provider.

    Supports both single-key (api_key) and multi-key (api_keys) configurations.
    When using single-key, internally converts to a pool with one entry.
    """

    def __init__(
        self, provider_config: ProviderConfig, strategy_override: Optional[str] = None
    ):
        self._lock = threading.Lock()
        self._entries: List[KeyEntry] = []
        strategy_name = strategy_override or provider_config.key_strategy or "priority"
        self._strategy: KeyStrategy = get_strategy(strategy_name)

        # Build key entries from provider config
        if provider_config.api_keys:
            for key_cfg in provider_config.api_keys:
                self._entries.append(KeyEntry(key_cfg))
        elif provider_config.api_key:
            # Single key → wrap as KeyConfig
            single = KeyConfig(key=provider_config.api_key, alias="default", priority=1)
            self._entries.append(KeyEntry(single))

    @property
    def size(self) -> int:
        return len(self._entries)

    @property
    def available_count(self) -> int:
        with self._lock:
            return sum(1 for e in self._entries if e.is_available)

    def get_key(self) -> str:
        """Select and return an API key string using the configured strategy.

        Raises KeyPoolExhaustedError if no keys are available.
        """
        with self._lock:
            entry = self._strategy.select(self._entries)
            if entry is None:
                raise KeyPoolExhaustedError(
                    f"All {len(self._entries)} keys are exhausted or unhealthy."
                )
            return entry.key

    def get_entry(self) -> KeyEntry:
        """Select and return a KeyEntry (with metadata) using the configured strategy."""
        with self._lock:
            entry = self._strategy.select(self._entries)
            if entry is None:
                raise KeyPoolExhaustedError(
                    f"All {len(self._entries)} keys are exhausted or unhealthy."
                )
            return entry

    def report_success(self, key: str, tokens: int = 0, cost_usd: float = 0.0):
        """Report a successful API call for usage tracking."""
        with self._lock:
            for entry in self._entries:
                if entry.key == key:
                    entry.report_success(tokens=tokens, cost_usd=cost_usd)
                    return

    def report_error(self, key: str):
        """Report a failed API call. After 3 consecutive errors, key is marked unhealthy."""
        with self._lock:
            for entry in self._entries:
                if entry.key == key:
                    entry.report_error()
                    return

    def reset_health(self, key: Optional[str] = None):
        """Reset health status. If key is None, reset all keys."""
        with self._lock:
            for entry in self._entries:
                if key is None or entry.key == key:
                    entry.healthy = True
                    entry.consecutive_errors = 0

    def status(self) -> List[Dict]:
        """Return status of all keys in the pool."""
        with self._lock:
            return [
                {
                    "alias": e.alias,
                    "healthy": e.healthy,
                    "available": e.is_available,
                    "requests": e.total_requests,
                    "tokens": e.total_tokens,
                    "cost_usd": round(e.total_cost_usd, 4),
                }
                for e in self._entries
            ]
