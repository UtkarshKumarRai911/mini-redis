"""
test_store.py — Unit tests for the Store class.

Run with: python -m pytest tests/ -v
"""

import time
import threading
import pytest
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from store.store import Store


# ── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def store():
    """Fresh store for each test."""
    return Store(max_keys=100)


# ── Basic GET / SET / DEL ─────────────────────────────────────────────────────

def test_set_and_get(store):
    assert store.set("key", "value") == "OK"
    assert store.get("key") == "value"

def test_get_missing_key(store):
    assert store.get("nonexistent") is None

def test_del_existing_key(store):
    store.set("k", "v")
    assert store.delete("k") == 1
    assert store.get("k") is None

def test_del_missing_key(store):
    assert store.delete("ghost") == 0

def test_del_multiple_keys(store):
    store.set("a", "1")
    store.set("b", "2")
    assert store.delete("a", "b", "c") == 2

def test_exists_present(store):
    store.set("x", "y")
    assert store.exists("x") == 1

def test_exists_missing(store):
    assert store.exists("missing") == 0

def test_overwrite_key(store):
    store.set("k", "v1")
    store.set("k", "v2")
    assert store.get("k") == "v2"


# ── TTL / EXPIRE ──────────────────────────────────────────────────────────────

def test_set_with_expiry(store):
    store.set("temp", "val", ex=1)
    assert store.get("temp") == "val"
    time.sleep(1.1)
    assert store.get("temp") is None

def test_ttl_no_expiry(store):
    store.set("k", "v")
    assert store.ttl("k") == -1

def test_ttl_with_expiry(store):
    store.set("k", "v", ex=10)
    remaining = store.ttl("k")
    assert 8 <= remaining <= 10

def test_ttl_expired_key(store):
    store.set("k", "v", ex=1)
    time.sleep(1.1)
    assert store.ttl("k") == -2

def test_ttl_missing_key(store):
    assert store.ttl("ghost") == -2

def test_expire_existing_key(store):
    store.set("k", "v")
    assert store.expire("k", 10) == 1
    assert store.ttl("k") > 0

def test_expire_missing_key(store):
    assert store.expire("ghost", 10) == 0


# ── KEYS / DBSIZE / FLUSHALL ──────────────────────────────────────────────────

def test_keys_all(store):
    store.set("a", "1")
    store.set("b", "2")
    assert sorted(store.keys("*")) == ["a", "b"]

def test_dbsize(store):
    store.set("a", "1")
    store.set("b", "2")
    assert store.dbsize() == 2

def test_flushall(store):
    store.set("a", "1")
    store.set("b", "2")
    store.flushall()
    assert store.dbsize() == 0

def test_keys_excludes_expired(store):
    store.set("alive", "yes")
    store.set("dead", "no", ex=1)
    time.sleep(1.1)
    keys = store.keys("*")
    assert "alive" in keys
    assert "dead" not in keys


# ── INCR / APPEND ─────────────────────────────────────────────────────────────

def test_incr_new_key(store):
    assert store.incr("counter") == 1

def test_incr_existing(store):
    store.set("counter", "5")
    assert store.incr("counter") == 6

def test_incr_non_integer(store):
    store.set("k", "notanumber")
    with pytest.raises(ValueError):
        store.incr("k")

def test_append_new_key(store):
    assert store.append("msg", "hello") == 5

def test_append_existing(store):
    store.set("msg", "hello")
    assert store.append("msg", " world") == 11
    assert store.get("msg") == "hello world"


# ── LRU eviction ─────────────────────────────────────────────────────────────

def test_lru_eviction():
    s = Store(max_keys=3)
    s.set("a", "1")
    s.set("b", "2")
    s.set("c", "3")
    # Access "a" to make it recently used
    s.get("a")
    # "b" is now LRU — adding "d" should evict "b"
    s.set("d", "4")
    assert s.get("b") is None   # evicted
    assert s.get("a") == "1"    # still present


# ── Concurrency ──────────────────────────────────────────────────────────────

def test_concurrent_incr():
    """Multiple threads incrementing the same counter — no race conditions."""
    s = Store()
    s.set("cnt", "0")
    threads = []
    for _ in range(100):
        t = threading.Thread(target=s.incr, args=("cnt",))
        threads.append(t)
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert s.get("cnt") == "100"


def test_concurrent_set_get():
    """Writers and readers running simultaneously — no crashes."""
    s = Store()
    errors = []

    def writer():
        for i in range(50):
            s.set(f"k{i}", str(i))

    def reader():
        for i in range(50):
            try:
                s.get(f"k{i}")
            except Exception as e:
                errors.append(e)

    threads = [threading.Thread(target=writer) for _ in range(5)]
    threads += [threading.Thread(target=reader) for _ in range(5)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
