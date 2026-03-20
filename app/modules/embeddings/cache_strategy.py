"""
Cache strategies for embedding service.

Implements Strategy Pattern for different caching approaches.
"""

from abc import ABC, abstractmethod
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Generic, TypeVar

K = TypeVar("K")
V = TypeVar("V")


@dataclass
class CacheStatistics:
    """Statistics for cache performance monitoring."""

    hits: int = 0
    misses: int = 0
    evictions: int = 0
    sets: int = 0

    @property
    def hit_rate(self) -> float:
        """Calculate cache hit rate as a percentage."""
        total = self.hits + self.misses
        return (self.hits / total * 100) if total > 0 else 0.0

    @property
    def total_requests(self) -> int:
        """Total number of cache requests."""
        return self.hits + self.misses

    def reset(self) -> None:
        """Reset all statistics to zero."""
        self.hits = 0
        self.misses = 0
        self.evictions = 0
        self.sets = 0


class CacheStrategy(ABC, Generic[K, V]):
    """Abstract base class for cache strategies."""

    def __init__(self, max_size: int = 1000) -> None:
        """
        Initialize cache strategy.

        Args:
            max_size: Maximum number of items to store in cache.
        """
        self._max_size = max_size
        self._stats = CacheStatistics()

    @abstractmethod
    def get(self, key: K) -> V | None:
        """
        Retrieve value from cache.

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found.
        """
        pass

    @abstractmethod
    def set(self, key: K, value: V) -> None:
        """
        Store value in cache.

        Args:
            key: Cache key.
            value: Value to cache.
        """
        pass

    @abstractmethod
    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of items cleared.
        """
        pass

    @abstractmethod
    def size(self) -> int:
        """
        Get current cache size.

        Returns:
            Number of items in cache.
        """
        pass

    def get_statistics(self) -> CacheStatistics:
        """
        Get cache statistics.

        Returns:
            Cache statistics object.
        """
        return self._stats

    def reset_statistics(self) -> None:
        """Reset cache statistics."""
        self._stats.reset()


class LRUCacheStrategy(CacheStrategy[K, V]):
    """
    Least Recently Used (LRU) cache strategy.

    Evicts the least recently accessed items when cache is full.
    """

    def __init__(self, max_size: int = 1000) -> None:
        """
        Initialize LRU cache.

        Args:
            max_size: Maximum number of items to store.
        """
        super().__init__(max_size)
        self._cache: OrderedDict[K, V] = OrderedDict()

    def get(self, key: K) -> V | None:
        """
        Retrieve value and move to end (most recent).

        Args:
            key: Cache key.

        Returns:
            Cached value or None if not found.
        """
        if key in self._cache:
            self._stats.hits += 1
            self._cache.move_to_end(key)
            return self._cache[key]
        self._stats.misses += 1
        return None

    def set(self, key: K, value: V) -> None:
        """
        Store value and evict LRU item if cache is full.

        Args:
            key: Cache key.
            value: Value to cache.
        """
        if key in self._cache:
            self._cache.move_to_end(key)
        else:
            if len(self._cache) >= self._max_size:
                self._cache.popitem(last=False)
                self._stats.evictions += 1

        self._cache[key] = value
        self._stats.sets += 1

    def clear(self) -> int:
        """
        Clear all cache entries.

        Returns:
            Number of items cleared.
        """
        size = len(self._cache)
        self._cache.clear()
        return size

    def size(self) -> int:
        """
        Get current cache size.

        Returns:
            Number of items in cache.
        """
        return len(self._cache)


class NoOpCacheStrategy(CacheStrategy[K, V]):
    """
    No-operation cache strategy that doesn't cache anything.

    Useful for testing or disabling cache.
    """

    def get(self, key: K) -> V | None:
        """Always returns None (cache miss)."""
        self._stats.misses += 1
        return None

    def set(self, key: K, value: V) -> None:
        """Does nothing."""
        self._stats.sets += 1

    def clear(self) -> int:
        """Returns 0 (nothing to clear)."""
        return 0

    def size(self) -> int:
        """Returns 0 (always empty)."""
        return 0
