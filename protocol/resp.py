"""
resp.py — RESP (Redis Serialization Protocol) parser and serializer.

RESP wire format (CN: application-layer protocol over TCP):
  Simple string : +OK\r\n
  Error         : -ERR message\r\n
  Integer       : :42\r\n
  Bulk string   : $6\r\nfoobar\r\n   ($-1\r\n = null)
  Array         : *3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n

This module:
  - RESPParser  : reads bytes from a socket and yields parsed commands
  - encode_*    : converts Python values back to RESP bytes to send
"""


class RESPError(Exception):
    pass


# ── Encoders (Python → RESP bytes) ──────────────────────────────────────────

def encode_simple_string(s: str) -> bytes:
    return f"+{s}\r\n".encode()

def encode_error(msg: str) -> bytes:
    return f"-{msg}\r\n".encode()

def encode_integer(n: int) -> bytes:
    return f":{n}\r\n".encode()

def encode_bulk_string(s) -> bytes:
    if s is None:
        return b"$-1\r\n"
    s = str(s)
    return f"${len(s)}\r\n{s}\r\n".encode()

def encode_array(items: list) -> bytes:
    if items is None:
        return b"*-1\r\n"
    parts = [f"*{len(items)}\r\n".encode()]
    for item in items:
        parts.append(encode_bulk_string(item))
    return b"".join(parts)

def encode_ok() -> bytes:
    return encode_simple_string("OK")

def encode_null() -> bytes:
    return b"$-1\r\n"


# ── Parser (RESP bytes → Python list of strings) ────────────────────────────

class RESPParser:
    """
    Stateful RESP parser.

    Usage:
        parser = RESPParser()
        parser.feed(data)          # feed raw bytes from socket
        while parser.has_command():
            cmd = parser.get_command()   # list of strings e.g. ['SET','k','v']
    """

    def __init__(self):
        self._buffer = b""
        self._commands = []

    def feed(self, data: bytes) -> None:
        """Append new bytes from the socket to internal buffer and parse."""
        self._buffer += data
        self._parse()

    def has_command(self) -> bool:
        return len(self._commands) > 0

    def get_command(self) -> list:
        return self._commands.pop(0)

    def _parse(self) -> None:
        """Try to extract complete RESP messages from buffer."""
        while self._buffer:
            if self._buffer[0:1] == b"*":
                result, consumed = self._parse_array(0)
                if result is None:
                    break   # incomplete — wait for more data
                self._commands.append(result)
                self._buffer = self._buffer[consumed:]
            else:
                # Inline command (e.g. plain text "PING\r\n")
                idx = self._buffer.find(b"\r\n")
                if idx == -1:
                    break
                line = self._buffer[:idx].decode(errors="replace").strip()
                self._buffer = self._buffer[idx + 2:]
                if line:
                    self._commands.append(line.split())

    def _parse_array(self, pos: int):
        """
        Parse a RESP array starting at pos.
        Returns (list_of_strings, bytes_consumed) or (None, 0) if incomplete.
        """
        end = self._buffer.find(b"\r\n", pos)
        if end == -1:
            return None, 0

        try:
            count = int(self._buffer[pos + 1:end])
        except ValueError:
            raise RESPError("Invalid array count")

        pos = end + 2
        items = []

        for _ in range(count):
            if pos >= len(self._buffer):
                return None, 0
            if self._buffer[pos:pos+1] != b"$":
                raise RESPError("Expected bulk string in array")

            end = self._buffer.find(b"\r\n", pos)
            if end == -1:
                return None, 0

            try:
                length = int(self._buffer[pos + 1:end])
            except ValueError:
                raise RESPError("Invalid bulk string length")

            pos = end + 2
            if length == -1:
                items.append(None)
                continue

            if pos + length + 2 > len(self._buffer):
                return None, 0   # incomplete bulk string

            value = self._buffer[pos:pos + length].decode(errors="replace")
            items.append(value)
            pos += length + 2   # skip \r\n after value

        return items, pos
