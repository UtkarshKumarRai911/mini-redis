"""
main.py — Entry point. Start the Mini-Redis server.

Usage:
    python main.py                        # default: 127.0.0.1:6380
    python main.py --port 6380
    python main.py --no-persist           # disable AOF logging
    python main.py --max-keys 500
"""

import argparse
from server.tcp_server import MiniRedisServer


def main():
    parser = argparse.ArgumentParser(description="Mini-Redis Server")
    parser.add_argument("--host",       default="127.0.0.1")
    parser.add_argument("--port",       type=int, default=6380)
    parser.add_argument("--max-keys",   type=int, default=1000,
                        help="Max keys before LRU eviction (default: 1000)")
    parser.add_argument("--aof-path",   default="appendonly.aof",
                        help="Path to AOF persistence file")
    parser.add_argument("--no-persist", action="store_true",
                        help="Disable AOF persistence")
    args = parser.parse_args()

    server = MiniRedisServer(
        host=args.host,
        port=args.port,
        max_keys=args.max_keys,
        aof_path=args.aof_path,
        persist=not args.no_persist,
    )
    server.start()


if __name__ == "__main__":
    main()
