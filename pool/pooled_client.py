"""
pooled_client.py — High-level Mini-Redis client using connection pooling.

Wraps ConnectionPool with Redis-like methods so callers don't deal
with raw RESP encoding — just call client.set('k', 'v').
"""

from pool.connection_pool import ConnectionPool
from protocol.resp import (
    make_resp_command,
    encode_simple_string, encode_bulk_string
)


def make_resp(*args) -> bytes:
    """Build RESP array command."""
    parts = [f"*{len(args)}\r\n".encode()]
    for a in args:
        a = str(a)
        parts.append(f"${len(a)}\r\n{a}\r\n".encode())
    return b"".join(parts)


def parse_response(data: bytes):
    """
    Simple RESP response parser — returns Python value.
    +OK       → 'OK'
    -ERR msg  → raises RuntimeError
    :42       → 42
    $5 hello  → 'hello'
    $-1       → None
    """
    if not data:
        return None
    prefix = chr(data[0])
    body = data[1:].decode(errors="replace").strip()

    if prefix == "+":
        return body
    elif prefix == "-":
        raise RuntimeError(body)
    elif prefix == ":":
        return int(body.split("\r\n")[0])
    elif prefix == "$":
        lines = data[1:].decode(errors="replace").split("\r\n")
        length = int(lines[0])
        if length == -1:
            return None
        return lines[1] if len(lines) > 1 else None
    else:
        return data.decode(errors="replace")


class PooledRedisClient:
    """
    Mini-Redis client backed by a connection pool.

    Example:
        client = PooledRedisClient(max_connections=10)
        client.set('name', 'utkarsh')
        print(client.get('name'))   # 'utkarsh'
        client.close()
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6380,
                 max_connections: int = 10):
        self._pool = ConnectionPool(
            host=host, port=port, max_connections=max_connections)

    def _cmd(self, *args):
        """Send a command and return parsed response."""
        with self._pool.get() as conn:
            resp = conn.send(make_resp(*args))
            return parse_response(resp)

    # ── Commands ─────────────────────────────────────────────────────────────

    def ping(self) -> str:
        return self._cmd("PING")

    def set(self, key: str, value: str, ex: int = None) -> str:
        if ex is not None:
            return self._cmd("SET", key, value, "EX", str(ex))
        return self._cmd("SET", key, value)

    def get(self, key: str):
        return self._cmd("GET", key)

    def delete(self, *keys: str) -> int:
        return self._cmd("DEL", *keys)

    def exists(self, key: str) -> int:
        return self._cmd("EXISTS", key)

    def expire(self, key: str, seconds: int) -> int:
        return self._cmd("EXPIRE", key, str(seconds))

    def ttl(self, key: str) -> int:
        return self._cmd("TTL", key)

    def incr(self, key: str) -> int:
        return self._cmd("INCR", key)

    def keys(self, pattern: str = "*") -> list:
        resp = self._cmd("KEYS", pattern)
        return resp if isinstance(resp, list) else []

    def dbsize(self) -> int:
        return self._cmd("DBSIZE")

    def flushall(self) -> str:
        return self._cmd("FLUSHALL")

    def pool_stats(self) -> dict:
        return self._pool.stats()

    def close(self) -> None:
        self._pool.close()
