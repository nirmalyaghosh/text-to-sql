"""
Unit tests for InProcessTTLCache.

Tests TTL expiry, LRU eviction, hit/miss counters,
and CacheBackend protocol conformance.
"""

import time

from text_to_sql.agents.cache import (
    CacheBackend,
    InProcessTTLCache,
)


class TestInProcessTTLCache:
    """
    Tests for InProcessTTLCache.
    """

    def test_clear_resets(self):
        """
        Clear empties cache and resets counters.
        """
        cache = InProcessTTLCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        cache.get("key1")  # hit
        cache.get("missing")  # miss
        cache.clear()
        assert cache.get("key1") is None
        assert cache.hits == 0
        # misses is 1 from the get("key1") after clear
        assert cache.misses == 1

    def test_conforms_to_protocol(self):
        """
        InProcessTTLCache satisfies CacheBackend.
        """
        cache = InProcessTTLCache()
        assert isinstance(cache, CacheBackend)

    def test_hit_miss_counters(self):
        """
        Counters track hits and misses.
        """
        cache = InProcessTTLCache(maxsize=10, ttl=60)
        cache.set("key1", "value1")
        cache.get("key1")  # hit
        cache.get("key1")  # hit
        cache.get("missing")  # miss
        assert cache.hits == 2
        assert cache.misses == 1

    def test_maxsize_eviction(self):
        """
        Oldest entry evicted when full.
        """
        cache = InProcessTTLCache(maxsize=2, ttl=60)
        cache.set("key1", "value1")
        cache.set("key2", "value2")
        cache.set("key3", "value3")
        # key1 should be evicted (LRU)
        assert cache.get("key1") is None
        assert cache.get("key2") == "value2"
        assert cache.get("key3") == "value3"

    def test_miss_returns_none(self):
        """
        Missing key returns None.
        """
        cache = InProcessTTLCache(maxsize=10, ttl=60)
        assert cache.get("nonexistent") is None

    def test_set_and_get(self):
        """
        Basic set/get round-trip.
        """
        cache = InProcessTTLCache(maxsize=10, ttl=60)
        cache.set("key1", {"data": "value1"})
        assert cache.get("key1") == {"data": "value1"}

    def test_ttl_expiry(self):
        """
        Entry expires after TTL.
        """
        cache = InProcessTTLCache(maxsize=10, ttl=1)
        cache.set("key1", "value1")
        assert cache.get("key1") == "value1"
        time.sleep(1.1)
        assert cache.get("key1") is None
