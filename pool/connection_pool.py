"""
connection_pool.py — TCP Connection Pool for Mini-Redis.

Problem without pooling:
  Every command creates a new TCP connection:
    connect() → send → recv → close()   ← 3-way handshake cost every time

Problem with pooling:
  Connections are created once and reused:
    borrow() → send → recv → return()   ← no handshake overhead

OS + CN concepts demonstrated:
  - Socket reuse          : avoid TCP 3-way handshake per command
  - threading.Semaphore   : OS primitive limiting concurrent borrows
  - threading.Lock        : protects the free-connection list
  - Context manager       : automatic return of connection to pool

Pool design:
  - Fixed size (max_connections)
  - Blocking borrow — if all connections in use, caller waits (Semaphore)
  - Health check on borrow — dead sockets are replaced automatically
  - Thread-safe — safe to use from multiple threads simultaneously
"""

import socket
import threading
import time
from contextlib import contextmanager


class PooledConnection:
    """
    A single TCP connection managed by the pool.
    Wraps a socket with send/recv helpers and health tracking.
    """

    def __init__(self, host: str, port: int, timeout: float = 5.0):
        self.host = host
        self.port = port
        self.timeout = timeout
        self._sock: socket.socket = None
        self.created_at = time.time()
        self.last_used = time.time()
        self._connect()

    def _connect(self) -> None:
        """Open a new TCP connection."""
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._sock.settimeout(self.timeout)
        self._sock.connect((self.host, self.port))

    def send(self, data: bytes) -> bytes:
        """Send data and read response. Raises on dead connection."""
        self._sock.sendall(data)
        response = b""
        while True:
            try:
                chunk = self._sock.recv(4096)
                if not chunk:
                    raise ConnectionResetError("Server closed connection")
                response += chunk
                if len(chunk) < 4096:
                    break
            except socket.timeout:
                break
        self.last_used = time.time()
        return response

    def is_alive(self) -> bool:
        """Quick health check — try a no-op PING."""
        try:
            # Send RESP inline PING
            self._sock.sendall(b"PING\r\n")
            resp = self._sock.recv(64)
            return resp.startswith(b"+PONG")
        except Exception:
            return False

    def close(self) -> None:
        try:
            self._sock.close()
        except Exception:
            pass


class ConnectionPool:
    """
    Thread-safe fixed-size TCP connection pool.

    Usage:
        pool = ConnectionPool(host='127.0.0.1', port=6380, max_connections=10)

        # Context manager (recommended):
        with pool.get() as conn:
            response = conn.send(b"PING\\r\\n")

        # Manual:
        conn = pool.borrow()
        conn.send(...)
        pool.return_connection(conn)

        pool.close()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6380,
                 max_connections: int = 10, timeout: float = 5.0,
                 max_idle_seconds: float = 60.0):
        """
        Args:
            host              : Mini-Redis server host
            port              : Mini-Redis server port
            max_connections   : pool size — max concurrent connections
            timeout           : socket read timeout in seconds
            max_idle_seconds  : evict connections idle longer than this
        """
        self._host = host
        self._port = port
        self._max = max_connections
        self._timeout = timeout
        self._max_idle = max_idle_seconds

        self._pool: list[PooledConnection] = []   # free connections
        self._lock = threading.Lock()              # protects _pool list
        # Semaphore: limits concurrent borrows to max_connections
        # OS concept: counting semaphore
        self._semaphore = threading.Semaphore(max_connections)

        # Pre-warm the pool — create all connections upfront
        for _ in range(max_connections):
            try:
                conn = PooledConnection(host, port, timeout)
                self._pool.append(conn)
            except Exception:
                pass   # server may not be up yet; connections created lazily

    # ── Public API ──────────────────────────────────────────────────────────

    def borrow(self) -> PooledConnection:
        """
        Borrow a connection from the pool.
        Blocks if all connections are in use (OS: semaphore wait).
        Returns a healthy PooledConnection.
        """
        self._semaphore.acquire()   # OS: blocks if pool exhausted

        with self._lock:
            # Try to reuse an existing idle connection
            while self._pool:
                conn = self._pool.pop()

                # Evict stale idle connections
                if time.time() - conn.last_used > self._max_idle:
                    conn.close()
                    continue

                # Return if healthy
                if conn.is_alive():
                    return conn
                else:
                    conn.close()

        # Pool was empty or all connections were dead — create a new one
        return PooledConnection(self._host, self._port, self._timeout)

    def return_connection(self, conn: PooledConnection) -> None:
        """Return a connection to the pool for reuse."""
        with self._lock:
            if len(self._pool) < self._max:
                self._pool.append(conn)
            else:
                conn.close()   # pool full — discard
        self._semaphore.release()   # OS: signal — one slot available

    @contextmanager
    def get(self):
        """
        Context manager for safe borrow + auto-return.

        with pool.get() as conn:
            response = conn.send(make_resp('SET', 'k', 'v'))
        # connection automatically returned to pool
        """
        conn = self.borrow()
        try:
            yield conn
        except Exception:
            # Connection may be broken — close it instead of returning
            conn.close()
            self._semaphore.release()
            raise
        else:
            self.return_connection(conn)

    def close(self) -> None:
        """Close all connections in the pool."""
        with self._lock:
            for conn in self._pool:
                conn.close()
            self._pool.clear()

    @property
    def size(self) -> int:
        """Number of idle connections currently in the pool."""
        with self._lock:
            return len(self._pool)

    def stats(self) -> dict:
        """Return pool statistics."""
        with self._lock:
            return {
                "max_connections": self._max,
                "idle_connections": len(self._pool),
                "in_use": self._max - len(self._pool),
            }
