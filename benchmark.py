"""
benchmark.py — Performance benchmark for Mini-Redis.

Measures throughput (operations/second) for:
  - SET
  - GET
  - INCR
  - Mixed (50% SET, 50% GET)
  - Concurrent clients (multithreaded)

Usage:
    python benchmark.py                     # default: 10,000 ops
    python benchmark.py --ops 50000
    python benchmark.py --ops 10000 --clients 10
"""

import socket
import time
import threading
import argparse
import statistics


# ── Low-level helpers ────────────────────────────────────────────────────────

def make_resp_command(*args) -> bytes:
    """Encode a command as RESP array bytes."""
    parts = [f"*{len(args)}\r\n".encode()]
    for arg in args:
        arg = str(arg)
        parts.append(f"${len(arg)}\r\n{arg}\r\n".encode())
    return b"".join(parts)


def send_recv(sock: socket.socket, data: bytes) -> bytes:
    sock.sendall(data)
    return sock.recv(4096)


def new_connection(host: str, port: int) -> socket.socket:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.connect((host, port))
    return s


# ── Single-client benchmarks ─────────────────────────────────────────────────

def bench_set(host, port, ops) -> float:
    s = new_connection(host, port)
    start = time.perf_counter()
    for i in range(ops):
        send_recv(s, make_resp_command("SET", f"key:{i}", f"value:{i}"))
    elapsed = time.perf_counter() - start
    s.close()
    return ops / elapsed


def bench_get(host, port, ops) -> float:
    # Pre-populate
    s = new_connection(host, port)
    for i in range(ops):
        send_recv(s, make_resp_command("SET", f"key:{i}", f"value:{i}"))

    start = time.perf_counter()
    for i in range(ops):
        send_recv(s, make_resp_command("GET", f"key:{i}"))
    elapsed = time.perf_counter() - start
    s.close()
    return ops / elapsed


def bench_incr(host, port, ops) -> float:
    s = new_connection(host, port)
    send_recv(s, make_resp_command("SET", "counter", "0"))
    start = time.perf_counter()
    for _ in range(ops):
        send_recv(s, make_resp_command("INCR", "counter"))
    elapsed = time.perf_counter() - start
    s.close()
    return ops / elapsed


def bench_mixed(host, port, ops) -> float:
    """50% SET, 50% GET interleaved."""
    s = new_connection(host, port)
    start = time.perf_counter()
    for i in range(ops):
        if i % 2 == 0:
            send_recv(s, make_resp_command("SET", f"m:{i}", f"v:{i}"))
        else:
            send_recv(s, make_resp_command("GET", f"m:{i-1}"))
    elapsed = time.perf_counter() - start
    s.close()
    return ops / elapsed


# ── Multi-client concurrent benchmark ────────────────────────────────────────

def bench_concurrent(host, port, ops_per_client, num_clients) -> float:
    """
    Each client runs in its own thread — simulates real concurrent load.
    OS concept: thread-level parallelism + shared Store mutex contention.
    """
    results = []
    lock = threading.Lock()

    def worker():
        s = new_connection(host, port)
        start = time.perf_counter()
        for i in range(ops_per_client):
            send_recv(s, make_resp_command("SET", f"c:{i}", f"v:{i}"))
        elapsed = time.perf_counter() - start
        s.close()
        with lock:
            results.append(ops_per_client / elapsed)

    threads = [threading.Thread(target=worker) for _ in range(num_clients)]
    start_all = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total_elapsed = time.perf_counter() - start_all

    total_ops = ops_per_client * num_clients
    return total_ops / total_elapsed


# ── Runner ────────────────────────────────────────────────────────────────────

def print_result(label: str, ops_per_sec: float, ops: int) -> None:
    print(f"  {label:<30} {ops_per_sec:>10,.0f} ops/sec  "
          f"({ops:,} ops in {ops/ops_per_sec*1000:.1f} ms)")


def main():
    parser = argparse.ArgumentParser(description="Mini-Redis Benchmark")
    parser.add_argument("--host",    default="127.0.0.1")
    parser.add_argument("--port",    type=int, default=6380)
    parser.add_argument("--ops",     type=int, default=10000,
                        help="Operations per benchmark (default: 10000)")
    parser.add_argument("--clients", type=int, default=10,
                        help="Concurrent clients for concurrency test (default: 10)")
    args = parser.parse_args()

    print(f"\n{'='*60}")
    print(f"  Mini-Redis Benchmark")
    print(f"  Host: {args.host}:{args.port}  |  Ops: {args.ops:,}  |  "
          f"Clients: {args.clients}")
    print(f"{'='*60}\n")

    # Verify server is up
    try:
        s = new_connection(args.host, args.port)
        s.close()
    except ConnectionRefusedError:
        print("ERROR: Server not running. Start with: python main.py")
        return

    benchmarks = [
        ("SET (single client)",   lambda: bench_set(args.host, args.port, args.ops)),
        ("GET (single client)",   lambda: bench_get(args.host, args.port, args.ops)),
        ("INCR (single client)",  lambda: bench_incr(args.host, args.port, args.ops)),
        ("Mixed SET+GET",         lambda: bench_mixed(args.host, args.port, args.ops)),
    ]

    for label, fn in benchmarks:
        try:
            ops_sec = fn()
            print_result(label, ops_sec, args.ops)
        except Exception as e:
            print(f"  {label:<30} ERROR: {e}")

    # Concurrent benchmark
    ops_per_client = args.ops // args.clients
    try:
        total_ops = ops_per_client * args.clients
        ops_sec = bench_concurrent(
            args.host, args.port, ops_per_client, args.clients)
        print_result(
            f"Concurrent ({args.clients} clients)",
            ops_sec, total_ops)
    except Exception as e:
        print(f"  Concurrent benchmark ERROR: {e}")

    # Pooled benchmark
    print()
    print("  -- Connection Pool (reused sockets) --")
    try:
        ops_sec = bench_pooled(args.host, args.port, args.ops, args.clients)
        print_result(
            f"Pooled SET ({args.clients} clients)",
            ops_sec, args.ops)
    except Exception as e:
        print(f"  Pooled benchmark ERROR: {e}")

    print(f"\n{'='*60}\n")


def bench_pooled(host, port, ops, pool_size=10) -> float:
    """
    Benchmark using connection pool — reuses connections instead of
    creating a new TCP socket per operation.
    """
    import sys, os
    sys.path.insert(0, os.path.dirname(__file__))
    from pool.connection_pool import ConnectionPool

    pool = ConnectionPool(host=host, port=port, max_connections=pool_size)
    results = []
    lock = threading.Lock()
    ops_per_thread = ops // pool_size

    def worker():
        start = time.perf_counter()
        for i in range(ops_per_thread):
            with pool.get() as conn:
                conn.send(make_resp_command("SET", f"p:{i}", f"v:{i}"))
        elapsed = time.perf_counter() - start
        with lock:
            results.append(ops_per_thread / elapsed)

    threads = [threading.Thread(target=worker) for _ in range(pool_size)]
    start_all = time.perf_counter()
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    total_elapsed = time.perf_counter() - start_all
    pool.close()
    return (ops_per_thread * pool_size) / total_elapsed


if __name__ == "__main__":
    main()
