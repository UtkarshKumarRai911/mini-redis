"""
store.py — Core in-memory key-value store.

Data structures used:
  - dict (HashMap)  : O(1) average GET / SET / DEL
  - dict (ttl_map)  : maps key -> expiry timestamp (float)
  - OrderedDict     : LRU eviction tracking (most-recent at end)

OOP concepts:
  - Encapsulation   : all state private, accessed via methods
  - Single responsibility : Store only manages data, not networking
"""

import time
import threading
from collections import OrderedDict


class Store:
    """
    Thread-safe in-memory key-value store with TTL and LRU eviction.
    """

    def __init__(self, max_keys: int = 1000):
        """
        Args:
            max_keys: maximum number of keys before LRU eviction kicks in.
        """
        self._data: OrderedDict = OrderedDict()   # key -> value (LRU order)
        self._ttl: dict = {}                       # key -> expiry epoch (float)
        self._max_keys = max_keys
        self._lock = threading.Lock()              # protects all state (OS: mutex)

    # ── Internal helpers ────────────────────────────────────────────────────

    def _is_expired(self, key: str) -> bool:
        """Return True if key has a TTL that has already passed."""
        if key in self._ttl:
            return time.time() > self._ttl[key]
        return False

    def _delete_expired(self, key: str) -> None:
        """Remove key and its TTL entry (caller must hold lock)."""
        self._data.pop(key, None)
        self._ttl.pop(key, None)

    def _evict_lru(self) -> None:
        """Evict the least-recently-used key (caller must hold lock)."""
        if self._data:
            lru_key, _ = next(iter(self._data.items()))
            self._delete_expired(lru_key)

    def _touch(self, key: str) -> None:
        """Move key to end of OrderedDict (marks as most-recently used)."""
        if key in self._data:
            self._data.move_to_end(key)

    # ── Public API ──────────────────────────────────────────────────────────

    def set(self, key: str, value: str, ex: int = None) -> str:
        """
        SET key value [EX seconds]
        Returns "OK".
        ex: optional expiry in seconds.
        """
        with self._lock:
            # Evict LRU if at capacity
            if key not in self._data and len(self._data) >= self._max_keys:
                self._evict_lru()

            self._data[key] = value
            self._touch(key)

            if ex is not None:
                self._ttl[key] = time.time() + ex
            else:
                self._ttl.pop(key, None)   # clear any previous TTL

        return "OK"

    def get(self, key: str):
        """
        GET key
        Returns value string, or None if not found / expired.
        """
        with self._lock:
            if key not in self._data:
                return None
            if self._is_expired(key):
                self._delete_expired(key)
                return None
            self._touch(key)
            return self._data[key]

    def delete(self, *keys: str) -> int:
        """
        DEL key [key ...]
        Returns number of keys actually deleted.
        """
        count = 0
        with self._lock:
            for key in keys:
                if key in self._data:
                    self._delete_expired(key)
                    count += 1
        return count

    def exists(self, key: str) -> int:
        """EXISTS key — returns 1 if key exists and not expired, else 0."""
        with self._lock:
            if key not in self._data:
                return 0
            if self._is_expired(key):
                self._delete_expired(key)
                return 0
            return 1

    def expire(self, key: str, seconds: int) -> int:
        """
        EXPIRE key seconds
        Returns 1 if TTL set, 0 if key does not exist.
        """
        with self._lock:
            if key not in self._data or self._is_expired(key):
                return 0
            self._ttl[key] = time.time() + seconds
            return 1

    def ttl(self, key: str) -> int:
        """
        TTL key
        Returns remaining seconds, -1 if no TTL, -2 if key missing/expired.
        """
        with self._lock:
            if key not in self._data:
                return -2
            if self._is_expired(key):
                self._delete_expired(key)
                return -2
            if key not in self._ttl:
                return -1
            remaining = int(self._ttl[key] - time.time())
            return max(remaining, 0)

    def keys(self, pattern: str = "*") -> list:
        """
        KEYS pattern
        Only supports '*' (all keys) for now.
        Returns list of non-expired keys.
        """
        with self._lock:
            expired = [k for k in self._data if self._is_expired(k)]
            for k in expired:
                self._delete_expired(k)

            if pattern == "*":
                return list(self._data.keys())

            # Basic prefix/suffix matching
            result = []
            for k in self._data:
                if pattern.startswith("*") and k.endswith(pattern[1:]):
                    result.append(k)
                elif pattern.endswith("*") and k.startswith(pattern[:-1]):
                    result.append(k)
                elif k == pattern:
                    result.append(k)
            return result

    def flushall(self) -> str:
        """FLUSHALL — delete all keys."""
        with self._lock:
            self._data.clear()
            self._ttl.clear()
        return "OK"

    def dbsize(self) -> int:
        """DBSIZE — return number of keys (excluding expired)."""
        with self._lock:
            expired = [k for k in self._data if self._is_expired(k)]
            for k in expired:
                self._delete_expired(k)
            return len(self._data)

    def incr(self, key: str) -> int:
        """
        INCR key — increment integer value by 1.
        Raises ValueError if value is not an integer.
        """
        with self._lock:
            if key not in self._data or self._is_expired(key):
                self._data[key] = "1"
                return 1
            try:
                new_val = int(self._data[key]) + 1
                self._data[key] = str(new_val)
                self._touch(key)
                return new_val
            except ValueError:
                raise ValueError("ERR value is not an integer or out of range")

    def append(self, key: str, value: str) -> int:
        """
        APPEND key value — append to existing string value.
        Returns new length of the string.
        """
        with self._lock:
            if key not in self._data or self._is_expired(key):
                self._data[key] = value
            else:
                self._data[key] += value
                self._touch(key)
            return len(self._data[key])
