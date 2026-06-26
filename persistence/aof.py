"""
aof.py — Append-Only File (AOF) persistence.

DBMS concept: Write-Ahead Logging (WAL).
Every write command is appended to a log file before returning OK.
On startup, the log is replayed in order to restore state — guaranteeing
zero data loss for any command that received an OK response.

Log format: one command per line, pipe-separated.
  SET|key|value
  SET|key|value|EX|30
  DEL|key1|key2
  EXPIRE|key|60
  FLUSHALL
"""

import os
import threading


# Commands that mutate state — only these are logged
WRITE_COMMANDS = {"SET", "DEL", "EXPIRE", "FLUSHALL", "INCR", "APPEND"}


class AOFWriter:
    """
    Appends write commands to the AOF log file.
    Thread-safe via a file lock.
    """

    def __init__(self, filepath: str = "appendonly.aof"):
        self._filepath = filepath
        self._lock = threading.Lock()
        self._file = open(self._filepath, "a", encoding="utf-8")

    def log(self, command: list) -> None:
        """
        Append a command to the AOF file.
        command: list of strings e.g. ['SET', 'foo', 'bar', 'EX', '10']
        """
        if not command:
            return
        if command[0].upper() not in WRITE_COMMANDS:
            return
        line = "|".join(str(part) for part in command) + "\n"
        with self._lock:
            self._file.write(line)
            self._file.flush()   # ensure durability — written to OS buffer

    def close(self) -> None:
        with self._lock:
            self._file.close()


class AOFLoader:
    """
    Reads the AOF file and replays commands against a Store on startup.
    """

    def __init__(self, filepath: str = "appendonly.aof"):
        self._filepath = filepath

    def exists(self) -> bool:
        return os.path.isfile(self._filepath)

    def replay(self, store) -> int:
        """
        Replay all commands in the AOF file against store.
        Returns number of commands replayed.
        """
        if not self.exists():
            return 0

        count = 0
        with open(self._filepath, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                parts = line.split("|")
                if not parts:
                    continue

                cmd = parts[0].upper()
                args = parts[1:]

                try:
                    if cmd == "SET":
                        # SET key value [EX seconds]
                        if len(args) >= 2:
                            key, value = args[0], args[1]
                            ex = None
                            if len(args) == 4 and args[2].upper() == "EX":
                                ex = int(args[3])
                            store.set(key, value, ex=ex)
                            count += 1

                    elif cmd == "DEL":
                        store.delete(*args)
                        count += 1

                    elif cmd == "EXPIRE":
                        if len(args) == 2:
                            store.expire(args[0], int(args[1]))
                            count += 1

                    elif cmd == "FLUSHALL":
                        store.flushall()
                        count += 1

                    elif cmd == "INCR":
                        if args:
                            store.incr(args[0])
                            count += 1

                    elif cmd == "APPEND":
                        if len(args) == 2:
                            store.append(args[0], args[1])
                            count += 1

                except Exception:
                    pass   # skip malformed lines

        return count
