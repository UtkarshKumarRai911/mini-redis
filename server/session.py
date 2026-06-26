"""
session.py — Per-client session (runs in its own thread).

OS concepts demonstrated:
  - Each client connection = one OS thread (threading.Thread)
  - Shared Store protected by mutex inside Store class
  - Socket I/O: recv() blocks until data arrives (blocking I/O)

DBMS concepts:
  - MULTI/EXEC implement atomic transactions:
      MULTI  → start transaction (queue subsequent commands)
      EXEC   → execute all queued commands atomically
      DISCARD → discard the queue and exit transaction mode
"""

import socket
from protocol.resp import RESPParser, encode_error, encode_array, encode_simple_string


class ClientSession:
    """
    Manages one connected client.
    Instantiated per connection, runs in its own thread.
    """

    def __init__(self, conn: socket.socket, addr, handler):
        self._conn = conn
        self._addr = addr
        self._handler = handler
        self._parser = RESPParser()

        # Transaction state (DBMS: transaction management)
        self._in_multi = False
        self._tx_queue = []

    def run(self) -> None:
        """Main loop: read data → parse → dispatch → send response."""
        print(f"[+] Client connected: {self._addr}")
        try:
            while True:
                try:
                    data = self._conn.recv(4096)
                except ConnectionResetError:
                    break

                if not data:
                    break   # client disconnected

                self._parser.feed(data)

                while self._parser.has_command():
                    command = self._parser.get_command()
                    response = self._dispatch(command)
                    self._conn.sendall(response)

        except Exception as e:
            print(f"[!] Session error {self._addr}: {e}")
        finally:
            self._conn.close()
            print(f"[-] Client disconnected: {self._addr}")

    def _dispatch(self, command: list) -> bytes:
        """
        Route command — handle MULTI/EXEC/DISCARD here,
        delegate everything else to CommandHandler.
        """
        if not command:
            return encode_error("ERR empty command")

        cmd = command[0].upper()

        # ── Transaction control ─────────────────────────────────────────────
        if cmd == "MULTI":
            if self._in_multi:
                return encode_error("ERR MULTI calls can not be nested")
            self._in_multi = True
            self._tx_queue = []
            return encode_simple_string("OK")

        if cmd == "DISCARD":
            if not self._in_multi:
                return encode_error("ERR DISCARD without MULTI")
            self._in_multi = False
            self._tx_queue = []
            return encode_simple_string("OK")

        if cmd == "EXEC":
            if not self._in_multi:
                return encode_error("ERR EXEC without MULTI")
            self._in_multi = False
            # Execute all queued commands and collect responses
            responses = []
            for queued_cmd in self._tx_queue:
                resp = self._handler.handle(queued_cmd, tx_queue=None)
                responses.append(resp)
            self._tx_queue = []
            # Return array of responses
            return (
                f"*{len(responses)}\r\n".encode() +
                b"".join(responses)
            )

        # ── Normal command or queue inside MULTI ────────────────────────────
        if self._in_multi:
            return self._handler.handle(command, tx_queue=self._tx_queue)
        else:
            return self._handler.handle(command, tx_queue=None)
