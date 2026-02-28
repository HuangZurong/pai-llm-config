"""Unit tests for pai_llm_config.keypool -- KeyEntry, strategies, and KeyPool."""

import threading

import pytest

from pai_llm_config.models import KeyConfig, ProviderConfig
from pai_llm_config.keypool.strategies import (
    KeyEntry,
    PriorityStrategy,
    RoundRobinStrategy,
    LeastUsedStrategy,
    RandomStrategy,
    get_strategy,
)
from pai_llm_config.keypool.pool import KeyPool, KeyPoolExhaustedError


# ============================================================
# Fixtures
# ============================================================


@pytest.fixture
def make_entry():
    """Factory fixture to create KeyEntry instances."""

    def _make(key="sk-test", alias=None, priority=None, daily_limit_usd=None):
        cfg = KeyConfig(
            key=key, alias=alias, priority=priority, daily_limit_usd=daily_limit_usd
        )
        return KeyEntry(cfg)

    return _make


@pytest.fixture
def single_key_provider():
    return ProviderConfig(type="openai", api_key="sk-single")


@pytest.fixture
def multi_key_provider():
    return ProviderConfig(
        type="openai",
        api_keys=[
            KeyConfig(key="sk-key1", alias="k1", priority=1),
            KeyConfig(key="sk-key2", alias="k2", priority=2),
            KeyConfig(key="sk-key3", alias="k3", priority=3),
        ],
        key_strategy="priority",
    )


@pytest.fixture
def no_key_provider():
    return ProviderConfig(type="openai")


# ============================================================
# TestKeyEntry
# ============================================================


class TestKeyEntry:
    def test_initial_state(self, make_entry):
        e = make_entry()
        assert e.healthy is True
        assert e.consecutive_errors == 0
        assert e.total_requests == 0
        assert e.total_tokens == 0
        assert e.total_cost_usd == 0.0
        assert e.is_available is True

    def test_alias_fallback_when_none(self, make_entry):
        e = make_entry(key="sk-abcdefghijk")
        assert e.alias == "sk-abcde..."

    def test_alias_from_config(self, make_entry):
        e = make_entry(alias="my-key")
        assert e.alias == "my-key"

    def test_priority_from_config(self, make_entry):
        e = make_entry(priority=5)
        assert e.priority == 5

    def test_priority_default(self, make_entry):
        e = make_entry()
        assert e.priority == 1

    def test_report_success(self, make_entry):
        e = make_entry()
        e.report_success(tokens=100, cost_usd=0.05)
        assert e.total_requests == 1
        assert e.total_tokens == 100
        assert e.total_cost_usd == pytest.approx(0.05)
        assert e.consecutive_errors == 0

    def test_report_success_resets_errors(self, make_entry):
        e = make_entry()
        e.report_error()
        e.report_error()
        assert e.consecutive_errors == 2
        e.report_success()
        assert e.consecutive_errors == 0
        assert e.healthy is True

    def test_report_error_increments(self, make_entry):
        e = make_entry()
        e.report_error()
        assert e.consecutive_errors == 1
        assert e.healthy is True

    def test_report_error_marks_unhealthy_after_three(self, make_entry):
        e = make_entry()
        for _ in range(3):
            e.report_error()
        assert e.consecutive_errors == 3
        assert e.healthy is False
        assert e.is_available is False

    def test_is_available_respects_daily_limit(self, make_entry):
        e = make_entry(daily_limit_usd=1.0)
        e.report_success(tokens=1000, cost_usd=1.0)
        assert e.is_available is False


# ============================================================
# TestPriorityStrategy
# ============================================================


class TestPriorityStrategy:
    def test_selects_lowest_priority(self, make_entry):
        keys = [make_entry(key="k3", priority=3), make_entry(key="k1", priority=1), make_entry(key="k2", priority=2)]
        selected = PriorityStrategy().select(keys)
        assert selected.key == "k1"

    def test_skips_unhealthy(self, make_entry):
        k1 = make_entry(key="k1", priority=1)
        k2 = make_entry(key="k2", priority=2)
        k1.healthy = False
        selected = PriorityStrategy().select([k1, k2])
        assert selected.key == "k2"

    def test_returns_none_when_all_exhausted(self, make_entry):
        k1 = make_entry(key="k1")
        k1.healthy = False
        assert PriorityStrategy().select([k1]) is None

    def test_single_key(self, make_entry):
        k1 = make_entry(key="k1")
        assert PriorityStrategy().select([k1]).key == "k1"


# ============================================================
# TestRoundRobinStrategy
# ============================================================


class TestRoundRobinStrategy:
    def test_rotates_through_keys(self, make_entry):
        keys = [make_entry(key=f"k{i}") for i in range(3)]
        strategy = RoundRobinStrategy()
        results = [strategy.select(keys).key for _ in range(6)]
        assert results == ["k0", "k1", "k2", "k0", "k1", "k2"]

    def test_skips_unavailable(self, make_entry):
        keys = [make_entry(key="k0"), make_entry(key="k1"), make_entry(key="k2")]
        keys[1].healthy = False
        strategy = RoundRobinStrategy()
        results = [strategy.select(keys).key for _ in range(4)]
        assert all(r in ("k0", "k2") for r in results)

    def test_returns_none_when_all_exhausted(self, make_entry):
        keys = [make_entry(key="k0")]
        keys[0].healthy = False
        assert RoundRobinStrategy().select(keys) is None

    def test_wraps_around(self, make_entry):
        keys = [make_entry(key=f"k{i}") for i in range(2)]
        strategy = RoundRobinStrategy()
        for _ in range(100):
            result = strategy.select(keys)
            assert result is not None


# ============================================================
# TestLeastUsedStrategy
# ============================================================


class TestLeastUsedStrategy:
    def test_selects_fewest_requests(self, make_entry):
        k1 = make_entry(key="k1")
        k2 = make_entry(key="k2")
        k1.total_requests = 5
        k2.total_requests = 0
        assert LeastUsedStrategy().select([k1, k2]).key == "k2"

    def test_skips_unavailable(self, make_entry):
        k1 = make_entry(key="k1")
        k2 = make_entry(key="k2")
        k1.total_requests = 5
        k2.total_requests = 0
        k2.healthy = False
        assert LeastUsedStrategy().select([k1, k2]).key == "k1"

    def test_returns_none_when_all_exhausted(self, make_entry):
        k1 = make_entry(key="k1")
        k1.healthy = False
        assert LeastUsedStrategy().select([k1]) is None


# ============================================================
# TestRandomStrategy
# ============================================================


class TestRandomStrategy:
    def test_returns_available_key(self, make_entry):
        keys = [make_entry(key=f"k{i}") for i in range(5)]
        for _ in range(20):
            result = RandomStrategy().select(keys)
            assert result.key in [f"k{i}" for i in range(5)]

    def test_skips_unavailable(self, make_entry):
        k1 = make_entry(key="k1")
        k2 = make_entry(key="k2")
        k1.healthy = False
        for _ in range(10):
            assert RandomStrategy().select([k1, k2]).key == "k2"

    def test_returns_none_when_all_exhausted(self, make_entry):
        k1 = make_entry(key="k1")
        k1.healthy = False
        assert RandomStrategy().select([k1]) is None


# ============================================================
# TestGetStrategy
# ============================================================


class TestGetStrategy:
    def test_known_strategies(self):
        assert isinstance(get_strategy("priority"), PriorityStrategy)
        assert isinstance(get_strategy("round_robin"), RoundRobinStrategy)
        assert isinstance(get_strategy("least_used"), LeastUsedStrategy)
        assert isinstance(get_strategy("random"), RandomStrategy)

    def test_unknown_raises(self):
        with pytest.raises(ValueError, match="Unknown key strategy"):
            get_strategy("nonexistent")

    def test_returns_new_instance(self):
        a = get_strategy("priority")
        b = get_strategy("priority")
        assert a is not b


# ============================================================
# TestKeyPool
# ============================================================


class TestKeyPool:
    def test_single_key_init(self, single_key_provider):
        pool = KeyPool(single_key_provider)
        assert pool.size == 1

    def test_multi_key_init(self, multi_key_provider):
        pool = KeyPool(multi_key_provider)
        assert pool.size == 3

    def test_no_key_init(self, no_key_provider):
        pool = KeyPool(no_key_provider)
        assert pool.size == 0

    def test_strategy_from_provider(self, multi_key_provider):
        pool = KeyPool(multi_key_provider)
        assert isinstance(pool._strategy, PriorityStrategy)

    def test_strategy_override(self, multi_key_provider):
        pool = KeyPool(multi_key_provider, strategy_override="round_robin")
        assert isinstance(pool._strategy, RoundRobinStrategy)

    def test_get_key_returns_string(self, single_key_provider):
        pool = KeyPool(single_key_provider)
        assert pool.get_key() == "sk-single"

    def test_get_key_raises_when_exhausted(self, single_key_provider):
        pool = KeyPool(single_key_provider)
        pool._entries[0].healthy = False
        with pytest.raises(KeyPoolExhaustedError, match="exhausted or unhealthy"):
            pool.get_key()

    def test_get_entry_returns_key_entry(self, single_key_provider):
        pool = KeyPool(single_key_provider)
        entry = pool.get_entry()
        assert isinstance(entry, KeyEntry)
        assert entry.key == "sk-single"

    def test_report_success(self, multi_key_provider):
        pool = KeyPool(multi_key_provider)
        pool.report_success("sk-key1", tokens=100, cost_usd=0.01)
        status = pool.status()
        k1 = next(s for s in status if s["alias"] == "k1")
        assert k1["requests"] == 1
        assert k1["tokens"] == 100

    def test_report_error_marks_unhealthy(self, multi_key_provider):
        pool = KeyPool(multi_key_provider)
        for _ in range(3):
            pool.report_error("sk-key1")
        status = pool.status()
        k1 = next(s for s in status if s["alias"] == "k1")
        assert k1["healthy"] is False
        assert k1["available"] is False

    def test_reset_health_all(self, multi_key_provider):
        pool = KeyPool(multi_key_provider)
        for key in ("sk-key1", "sk-key2"):
            for _ in range(3):
                pool.report_error(key)
        assert pool.available_count == 1
        pool.reset_health()
        assert pool.available_count == 3

    def test_reset_health_single(self, multi_key_provider):
        pool = KeyPool(multi_key_provider)
        for _ in range(3):
            pool.report_error("sk-key1")
        assert pool.available_count == 2
        pool.reset_health("sk-key1")
        assert pool.available_count == 3

    def test_status_returns_list(self, multi_key_provider):
        pool = KeyPool(multi_key_provider)
        status = pool.status()
        assert len(status) == 3
        assert all(
            {"alias", "healthy", "available", "requests", "tokens", "cost_usd"}
            == set(s.keys())
            for s in status
        )

    def test_available_count(self, multi_key_provider):
        pool = KeyPool(multi_key_provider)
        assert pool.available_count == 3
        pool._entries[0].healthy = False
        assert pool.available_count == 2

    def test_thread_safety(self, multi_key_provider):
        pool = KeyPool(multi_key_provider, strategy_override="round_robin")
        results = []
        errors = []

        def worker():
            try:
                for _ in range(50):
                    key = pool.get_key()
                    results.append(key)
            except Exception as exc:
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(10)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
        assert len(results) == 500
        assert all(r in ("sk-key1", "sk-key2", "sk-key3") for r in results)

    def test_get_key_empty_pool_raises(self, no_key_provider):
        pool = KeyPool(no_key_provider)
        with pytest.raises(KeyPoolExhaustedError):
            pool.get_key()

    def test_get_entry_exhausted_raises(self, single_key_provider):
        pool = KeyPool(single_key_provider)
        pool._entries[0].healthy = False
        with pytest.raises(KeyPoolExhaustedError):
            pool.get_entry()

    def test_report_success_unknown_key_is_noop(self, multi_key_provider):
        pool = KeyPool(multi_key_provider)
        pool.report_success("sk-nonexistent", tokens=100)
        # All entries unchanged
        assert all(s["requests"] == 0 for s in pool.status())

    def test_report_error_unknown_key_is_noop(self, multi_key_provider):
        pool = KeyPool(multi_key_provider)
        pool.report_error("sk-nonexistent")
        assert all(s["healthy"] is True for s in pool.status())
