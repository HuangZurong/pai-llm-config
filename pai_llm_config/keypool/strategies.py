"""Key selection strategies for multi-key pool management."""

import random as _random
import threading
from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import KeyConfig


class KeyEntry:
    """Runtime state for a single API key."""

    def __init__(self, config: KeyConfig):
        self.config = config
        self.key: str = config.key
        self.alias: str = config.alias or config.key[:8] + "..."
        self.priority: int = config.priority or 1
        self.healthy: bool = True
        self.consecutive_errors: int = 0
        self.total_requests: int = 0
        self.total_tokens: int = 0
        self.total_cost_usd: float = 0.0

    def report_success(self, tokens: int = 0, cost_usd: float = 0.0):
        self.consecutive_errors = 0
        self.healthy = True
        self.total_requests += 1
        self.total_tokens += tokens
        self.total_cost_usd += cost_usd

    def report_error(self):
        self.consecutive_errors += 1
        if self.consecutive_errors >= 3:
            self.healthy = False

    @property
    def is_available(self) -> bool:
        """Check if key is healthy and within limits."""
        if not self.healthy:
            return False
        cfg = self.config
        if cfg.daily_limit_usd and self.total_cost_usd >= cfg.daily_limit_usd:
            return False
        return True

    def __repr__(self) -> str:
        status = "✓" if self.is_available else "✗"
        return f"KeyEntry({self.alias} [{status}] reqs={self.total_requests})"


class KeyStrategy(ABC):
    """Base class for key selection strategies."""

    @abstractmethod
    def select(self, keys: List[KeyEntry]) -> Optional[KeyEntry]:
        """Select a key from available keys."""
        ...


class PriorityStrategy(KeyStrategy):
    """Select the highest-priority available key (lowest priority number)."""

    def select(self, keys: List[KeyEntry]) -> Optional[KeyEntry]:
        available = [k for k in keys if k.is_available]
        if not available:
            return None
        return min(available, key=lambda k: k.priority)


class RoundRobinStrategy(KeyStrategy):
    """Rotate through available keys in order."""

    def __init__(self):
        self._index = 0
        self._lock = threading.Lock()

    def select(self, keys: List[KeyEntry]) -> Optional[KeyEntry]:
        available = [k for k in keys if k.is_available]
        if not available:
            return None
        with self._lock:
            idx = self._index % len(available)
            self._index += 1
            return available[idx]


class LeastUsedStrategy(KeyStrategy):
    """Select the key with fewest total requests."""

    def select(self, keys: List[KeyEntry]) -> Optional[KeyEntry]:
        available = [k for k in keys if k.is_available]
        if not available:
            return None
        return min(available, key=lambda k: k.total_requests)


class RandomStrategy(KeyStrategy):
    """Select a random available key."""

    def select(self, keys: List[KeyEntry]) -> Optional[KeyEntry]:
        available = [k for k in keys if k.is_available]
        if not available:
            return None
        return _random.choice(available)


_STRATEGIES = {
    "priority": PriorityStrategy,
    "round_robin": RoundRobinStrategy,
    "least_used": LeastUsedStrategy,
    "random": RandomStrategy,
}


def get_strategy(name: str) -> KeyStrategy:
    """Get a strategy instance by name."""
    cls = _STRATEGIES.get(name)
    if cls is None:
        raise ValueError(
            f"Unknown key strategy: '{name}'. "
            f"Available: {', '.join(_STRATEGIES.keys())}"
        )
    return cls()
