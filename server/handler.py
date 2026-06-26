"""
handler.py — Command dispatcher.

Takes a parsed command (list of strings) and routes it to the correct
Store method, returning a RESP-encoded response.

Supported commands:
  PING, ECHO
  SET, GET, DEL, EXISTS
  EXPIRE, TTL
  KEYS, DBSIZE, FLUSHALL
  INCR, APPEND
  MULTI, EXEC, DISCARD   (transactions)
"""

from protocol.resp import (
    encode_ok, encode_error, encode_bulk_string,
    encode_integer, encode_array, encode_simple_string
)


class CommandHandler:
    """
    Stateless command dispatcher.
    One instance shared across all client threads.
    """

    def __init__(self, store, aof_writer=None):
        self._store = store
        self._aof = aof_writer

    def handle(self, command: list, tx_queue: list = None) -> bytes:
        """
        Process one command.

        Args:
            command   : list of strings e.g. ['SET', 'k', 'v']
            tx_queue  : if not None, we are inside a MULTI transaction —
                        queue the command instead of executing it.

        Returns RESP-encoded bytes.
        """
        if not command:
            return encode_error("ERR empty command")

        cmd = command[0].upper()
        args = command[1:]

        # ── Transaction queuing ─────────────────────────────────────────────
        # MULTI/EXEC/DISCARD handled by ClientSession — not queued
        if tx_queue is not None and cmd not in ("EXEC", "DISCARD"):
            tx_queue.append(command)
            return encode_simple_string("QUEUED")

        # ── Route command ───────────────────────────────────────────────────
        try:
            if cmd == "PING":
                return encode_simple_string("PONG" if not args else args[0])

            elif cmd == "ECHO":
                if not args:
                    return encode_error("ERR wrong number of arguments for ECHO")
                return encode_bulk_string(args[0])

            elif cmd == "SET":
                return self._cmd_set(args)

            elif cmd == "GET":
                if len(args) != 1:
                    return encode_error("ERR wrong number of arguments for GET")
                val = self._store.get(args[0])
                return encode_bulk_string(val)

            elif cmd == "DEL":
                if not args:
                    return encode_error("ERR wrong number of arguments for DEL")
                count = self._store.delete(*args)
                self._log(command)
                return encode_integer(count)

            elif cmd == "EXISTS":
                if not args:
                    return encode_error("ERR wrong number of arguments for EXISTS")
                return encode_integer(self._store.exists(args[0]))

            elif cmd == "EXPIRE":
                if len(args) != 2:
                    return encode_error("ERR wrong number of arguments for EXPIRE")
                result = self._store.expire(args[0], int(args[1]))
                self._log(command)
                return encode_integer(result)

            elif cmd == "TTL":
                if len(args) != 1:
                    return encode_error("ERR wrong number of arguments for TTL")
                return encode_integer(self._store.ttl(args[0]))

            elif cmd == "KEYS":
                pattern = args[0] if args else "*"
                return encode_array(self._store.keys(pattern))

            elif cmd == "DBSIZE":
                return encode_integer(self._store.dbsize())

            elif cmd == "FLUSHALL":
                self._store.flushall()
                self._log(command)
                return encode_ok()

            elif cmd == "INCR":
                if len(args) != 1:
                    return encode_error("ERR wrong number of arguments for INCR")
                try:
                    val = self._store.incr(args[0])
                    self._log(command)
                    return encode_integer(val)
                except ValueError as e:
                    return encode_error(str(e))

            elif cmd == "APPEND":
                if len(args) != 2:
                    return encode_error("ERR wrong number of arguments for APPEND")
                length = self._store.append(args[0], args[1])
                self._log(command)
                return encode_integer(length)

            elif cmd == "COMMAND":
                # redis-cli sends this on connect — return empty array
                return encode_array([])

            else:
                return encode_error(f"ERR unknown command '{cmd}'")

        except Exception as e:
            return encode_error(f"ERR {str(e)}")

    def _cmd_set(self, args: list) -> bytes:
        """Handle SET key value [EX seconds] [PX milliseconds]."""
        if len(args) < 2:
            return encode_error("ERR wrong number of arguments for SET")

        key, value = args[0], args[1]
        ex = None

        i = 2
        while i < len(args):
            opt = args[i].upper()
            if opt == "EX":
                if i + 1 >= len(args):
                    return encode_error("ERR syntax error")
                try:
                    ex = int(args[i + 1])
                except ValueError:
                    return encode_error("ERR value is not an integer")
                i += 2
            elif opt == "PX":
                if i + 1 >= len(args):
                    return encode_error("ERR syntax error")
                try:
                    ex = int(args[i + 1]) // 1000   # convert ms to seconds
                except ValueError:
                    return encode_error("ERR value is not an integer")
                i += 2
            else:
                return encode_error(f"ERR syntax error near '{args[i]}'")

        self._store.set(key, value, ex=ex)

        # Log to AOF — include EX if set
        log_cmd = ["SET", key, value]
        if ex is not None:
            log_cmd += ["EX", str(ex)]
        self._log(log_cmd)

        return encode_ok()

    def _log(self, command: list) -> None:
        """Write command to AOF if persistence is enabled."""
        if self._aof:
            self._aof.log(command)
