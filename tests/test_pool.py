"""
test_pool.py — Unit tests for ConnectionPool.

These tests require the Mini-Redis server to be running on port 6380.
Skip gracefully if server is not available.

Run: python -m pytest tests/test_pool.py -v
"""

import threading
import socket
import time
import pytest
import sys, os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from pool.connection_pool import ConnectionPool, PooledConnection


# ── Helpers ──────────────────────────────────────────────────────────────────

def server_available(host="127.0.0.1", port=6380) -> bool:
    try:
        s = socket.socket()
        s.settimeout(1)
        s.connect((host, port))
        s.close()
        return True
    except Exception:
        return False


skip_if_no_server = pytest.mark.skipif(
    not server_available(),
    reason="Mini-Redis server not running on 127.0.0.1:6380"
)

def make_resp(*args) -> bytes:
    parts = [f"*{len(args)}\r\n".encode()]
    for a in args:
        a = str(a)
        parts.append(f"${len(a)}\r\n{a}\r\n".encode())
    return b"".join(parts)


# ── Tests ─────────────────────────────────────────────────────────────────────

@skip_if_no_server
def test_pool_basic_borrow_return():
    pool = ConnectionPool(max_connections=3)
    conn = pool.borrow()
    assert conn is not None
    pool.return_connection(conn)
    assert pool.size == 3   # back to full
    pool.close()


@skip_if_no_server
def test_pool_context_manager():
    pool = ConnectionPool(max_connections=3)
    with pool.get() as conn:
        resp = conn.send(b"PING\r\n")
        assert b"PONG" in resp
    assert pool.size == 3   # returned after context exit
    pool.close()


@skip_if_no_server
def test_pool_set_get_via_connection():
    pool = ConnectionPool(max_connections=3)
    with pool.get() as conn:
        conn.send(make_resp("SET", "pool_test", "hello"))
    with pool.get() as conn:
        resp = conn.send(make_resp("GET", "pool_test"))
        assert b"hello" in resp
    pool.close()


@skip_if_no_server
def test_pool_concurrent_borrows():
    """
    10 threads each borrow a connection, do a SET, return it.
    Pool size = 5 — some threads must wait (semaphore blocking).
    No deadlocks or errors expected.
    """
    pool = ConnectionPool(max_connections=5)
    errors = []

    def worker(i):
        try:
            with pool.get() as conn:
                conn.send(make_resp("SET", f"pool:key:{i}", str(i)))
                time.sleep(0.01)   # hold connection briefly
        except Exception as e:
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(errors) == 0
    assert pool.size <= 5
    pool.close()


@skip_if_no_server
def test_pool_stats():
    pool = ConnectionPool(max_connections=5)
    stats = pool.stats()
    assert stats["max_connections"] == 5
    assert stats["idle_connections"] <= 5
    pool.close()


@skip_if_no_server
def test_pool_exhaustion_blocks_then_releases():
    """
    Borrow all connections, then return one — next borrow should succeed.
    """
    pool = ConnectionPool(max_connections=2)
    c1 = pool.borrow()
    c2 = pool.borrow()

    released = threading.Event()
    result = []

    def late_borrower():
        # This will block until a connection is returned
        conn = pool.borrow()
        result.append(conn)
        pool.return_connection(conn)

    t = threading.Thread(target=late_borrower)
    t.start()
    time.sleep(0.1)   # t is blocking on semaphore

    pool.return_connection(c1)   # release one → t unblocks
    t.join(timeout=2)

    assert len(result) == 1   # late_borrower got a connection
    pool.return_connection(c2)
    pool.close()
