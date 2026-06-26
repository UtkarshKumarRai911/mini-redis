"""
tcp_server.py — TCP server (CN: transport layer, socket programming).

OS + CN concepts:
  - socket.socket(AF_INET, SOCK_STREAM) : TCP socket (reliable, ordered)
  - SO_REUSEADDR                        : reuse port immediately after restart
  - server.listen(backlog)              : OS connection queue
  - server.accept()                     : blocks until a client connects
  - threading.Thread per client         : concurrent handling (OS threads)
  - daemon=True                         : threads die when main process exits
"""

import socket
import threading

from store.store import Store
from server.handler import CommandHandler
from server.session import ClientSession
from persistence.aof import AOFWriter, AOFLoader


class MiniRedisServer:
    """
    TCP server that accepts Redis clients and handles commands.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 6380,
                 max_keys: int = 1000, aof_path: str = "appendonly.aof",
                 persist: bool = True):
        self._host = host
        self._port = port
        self._store = Store(max_keys=max_keys)
        self._aof_writer = AOFWriter(aof_path) if persist else None
        self._handler = CommandHandler(self._store, self._aof_writer)
        self._persist = persist
        self._aof_path = aof_path

    def start(self) -> None:
        # ── Restore state from AOF ──────────────────────────────────────────
        if self._persist:
            loader = AOFLoader(self._aof_path)
            count = loader.replay(self._store)
            if count:
                print(f"[AOF] Restored {count} commands from {self._aof_path}")

        # ── Create TCP socket ───────────────────────────────────────────────
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind((self._host, self._port))
        server.listen(128)   # OS backlog queue

        print(f"[*] Mini-Redis listening on {self._host}:{self._port}")
        print(f"[*] Connect with: redis-cli -p {self._port}")
        print(f"[*] Or run: python client.py")
        print(f"[*] Press Ctrl+C to stop\n")

        try:
            while True:
                conn, addr = server.accept()   # blocks (OS: blocking I/O)
                # Spawn a new thread per client (OS: multithreading)
                t = threading.Thread(
                    target=self._handle_client,
                    args=(conn, addr),
                    daemon=True
                )
                t.start()
        except KeyboardInterrupt:
            print("\n[*] Shutting down...")
        finally:
            if self._aof_writer:
                self._aof_writer.close()
            server.close()

    def _handle_client(self, conn: socket.socket, addr) -> None:
        """Entry point for each client thread."""
        session = ClientSession(conn, addr, self._handler)
        session.run()
