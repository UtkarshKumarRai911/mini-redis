"""
test_protocol.py — Unit tests for the RESP protocol parser and encoders.
"""

import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from protocol.resp import (
    RESPParser,
    encode_simple_string, encode_error, encode_integer,
    encode_bulk_string, encode_array, encode_ok, encode_null
)


# ── Encoders ─────────────────────────────────────────────────────────────────

def test_encode_simple_string():
    assert encode_simple_string("OK") == b"+OK\r\n"

def test_encode_error():
    assert encode_error("ERR bad") == b"-ERR bad\r\n"

def test_encode_integer():
    assert encode_integer(42) == b":42\r\n"

def test_encode_bulk_string():
    assert encode_bulk_string("hello") == b"$5\r\nhello\r\n"

def test_encode_bulk_string_null():
    assert encode_bulk_string(None) == b"$-1\r\n"

def test_encode_ok():
    assert encode_ok() == b"+OK\r\n"

def test_encode_null():
    assert encode_null() == b"$-1\r\n"

def test_encode_array():
    result = encode_array(["foo", "bar"])
    assert result == b"*2\r\n$3\r\nfoo\r\n$3\r\nbar\r\n"

def test_encode_array_empty():
    assert encode_array([]) == b"*0\r\n"


# ── Parser ────────────────────────────────────────────────────────────────────

def test_parse_inline_ping():
    p = RESPParser()
    p.feed(b"PING\r\n")
    assert p.has_command()
    assert p.get_command() == ["PING"]

def test_parse_resp_array_set():
    p = RESPParser()
    p.feed(b"*3\r\n$3\r\nSET\r\n$3\r\nfoo\r\n$3\r\nbar\r\n")
    assert p.has_command()
    assert p.get_command() == ["SET", "foo", "bar"]

def test_parse_resp_array_get():
    p = RESPParser()
    p.feed(b"*2\r\n$3\r\nGET\r\n$3\r\nfoo\r\n")
    assert p.has_command()
    assert p.get_command() == ["GET", "foo"]

def test_parse_multiple_commands():
    p = RESPParser()
    p.feed(b"PING\r\nPING\r\n")
    assert p.has_command()
    p.get_command()
    assert p.has_command()
    p.get_command()
    assert not p.has_command()

def test_parse_partial_command():
    """Incomplete data should not yield a command."""
    p = RESPParser()
    p.feed(b"*3\r\n$3\r\nSET\r\n")   # incomplete
    assert not p.has_command()
    p.feed(b"$3\r\nfoo\r\n$3\r\nbar\r\n")
    assert p.has_command()
    assert p.get_command() == ["SET", "foo", "bar"]

def test_parse_del_multiple():
    p = RESPParser()
    p.feed(b"*3\r\n$3\r\nDEL\r\n$1\r\na\r\n$1\r\nb\r\n")
    assert p.has_command()
    assert p.get_command() == ["DEL", "a", "b"]
