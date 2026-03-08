"""
Cache backend protocol and in-process TTL implementation.

Defines a swappable CacheBackend protocol so the schema
pruning cache can be replaced with Redis (or similar)
without changing agent code.
"""

from typing import (
    Any,
    Optional,
    Protocol,
    runtime_checkable,
)

from cachetools import TTLCache

from text_to_sql.app_logger import get_logger


logger = get_logger(__name__)


@runtime_checkable
class CacheBackend(Protocol):
    """
    Protocol for swappable cache backends.

    In-process TTL cache for single-instance deployments.
    Swap with a Redis-backed implementation for
    multi-instance deployments. The interface stays
    the same.
    """

    def get(
        self, key: str,
    ) -> Optional[Any]:
        """
        Retrieve a cached value by key.
        """
        ...

    def set(
        self, key: str, value: Any,
    ) -> None:
        """
        Store a value in the cache.
        """
        ...

    def clear(self) -> None:
        """
        Clear all entries and reset counters.
        """
        ...

    @property
    def hits(self) -> int:
        """
        Total cache hits since last clear.
        """
        ...

    @property
    def misses(self) -> int:
        """
        Total cache misses since last clear.
        """
        ...


class InProcessTTLCache:
    """
    In-process TTL cache with LRU eviction.

    For single-instance deployments. For multi-instance,
    swap with a Redis-backed implementation that
    conforms to the same CacheBackend protocol.

    Args:
        maxsize: Maximum number of cached entries
            (default: 128)
        ttl: Time-to-live in seconds (default: 300).
            Entries expire after this duration to
            account for schema changes.
    """

    def __init__(
        self,
        maxsize: int = 128,
        ttl: int = 300,
    ):
        self._cache: TTLCache = TTLCache(
            maxsize=maxsize, ttl=ttl
        )
        self._hits = 0
        self._misses = 0

    def clear(self) -> None:
        """
        Clear all entries and reset counters.
        """
        self._cache.clear()
        self._hits = 0
        self._misses = 0

    def get(self, key: str) -> Optional[Any]:
        """
        Retrieve a cached value by key.

        Returns None on miss. Increments hit/miss
        counters for observability.
        """
        val = self._cache.get(key)
        if val is not None:
            self._hits += 1
            return val
        self._misses += 1
        return None

    def set(self, key: str, value: Any) -> None:
        """
        Store a value in the cache.
        """
        self._cache[key] = value

    @property
    def hits(self) -> int:
        """
        Total cache hits since last clear.
        """
        return self._hits

    @property
    def misses(self) -> int:
        """
        Total cache misses since last clear.
        """
        return self._misses
