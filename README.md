# 🗄️ Mini-Redis

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?style=for-the-badge&logo=python&logoColor=white"/>
  <img src="https://img.shields.io/badge/Protocol-RESP-FF6B35?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Persistence-AOF-22C55E?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Transactions-MULTI%2FEXEC-8B5CF6?style=for-the-badge"/>
  <img src="https://img.shields.io/badge/Tests-42%20passing-2563EB?style=for-the-badge"/>
</p>

<p align="center">
  <b>A Redis clone built from scratch — TCP server · RESP protocol · AOF persistence · LRU eviction · Transactions</b>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/SET-21%2C026_ops%2Fsec-22C55E?style=flat-square"/>
  <img src="https://img.shields.io/badge/GET-30%2C140_ops%2Fsec-2563EB?style=flat-square"/>
  <img src="https://img.shields.io/badge/Concurrent_10_clients-29%2C241_ops%2Fsec-8B5CF6?style=flat-square"/>
</p>

---

## 📋 Table of Contents

- [Overview](#overview)
- [CS Concepts Covered](#cs-concepts-covered)
- [Architecture](#architecture)
- [Supported Commands](#supported-commands)
- [Benchmark Results](#benchmark-results)
- [Quick Start](#quick-start)
- [Project Structure](#project-structure)
- [Design Decisions](#design-decisions)
- [Running Tests](#running-tests)

---

## Overview

Mini-Redis is a functional Redis-compatible in-memory key-value store built entirely from scratch in Python — no Redis libraries used. It implements the actual Redis wire protocol (RESP), accepts connections from real Redis clients (`redis-cli`), persists data to disk using Append-Only File logging, and handles concurrent clients using OS threads.

Built to demonstrate core Computer Science concepts: **OOP**, **OS (threading/concurrency)**, **Computer Networks (TCP sockets/protocol design)**, and **DBMS (persistence/transactions)**.

---

## CS Concepts Covered

| Subject | Implementation |
|---|---|
| **OOP** | `Store`, `CommandHandler`, `ClientSession`, `MiniRedisServer`, `AOFWriter` — each with single responsibility and encapsulated state |
| **OS** | One thread per client (`threading.Thread`), mutex locks (`threading.Lock`) for shared store, background TTL expiry daemon thread |
| **Computer Networks** | Raw TCP server (`socket.SOCK_STREAM`), custom application-layer protocol (RESP), `SO_REUSEADDR`, connection backlog queue |
| **DBMS** | AOF Write-Ahead Logging, full state restore on startup, MULTI/EXEC atomic transactions with command queuing and rollback |
| **DSA** | `OrderedDict` for O(1) GET/SET + LRU eviction, min-heap-style TTL via epoch timestamps, HashMap for O(1) key lookup |

---

## Architecture

```
Client (redis-cli / python client.py)
            │
            │  TCP connection (CN: SOCK_STREAM)
            ▼
┌───────────────────────────────────┐
│         MiniRedisServer            │
│   socket.accept() → new Thread    │  ← OS: one thread per client
└──────────────┬────────────────────┘
               │
               ▼
┌───────────────────────────────────┐
│          ClientSession             │
│  RESPParser → parse bytes         │  ← CN: RESP protocol parsing
│  MULTI/EXEC transaction state     │  ← DBMS: transaction management
└──────────────┬────────────────────┘
               │
               ▼
┌───────────────────────────────────┐
│         CommandHandler             │
│  Routes: SET/GET/DEL/EXPIRE/...   │
│  Calls AOFWriter.log() on writes  │  ← DBMS: Write-Ahead Logging
└──────────────┬────────────────────┘
               │
    ┌──────────┴──────────┐
    ▼                     ▼
┌─────────┐        ┌─────────────┐
│  Store   │        │  AOFWriter  │
│ OrderedDict (LRU) │  appendonly.aof │
│ TTL dict │        │  (disk log) │
│ Mutex    │        └─────────────┘
└─────────┘         ← restored on startup by AOFLoader
```

---

## Supported Commands

| Command | Description |
|---|---|
| `PING` | Returns PONG |
| `SET key value [EX seconds]` | Set key with optional expiry |
| `GET key` | Get value (returns nil if expired) |
| `DEL key [key ...]` | Delete one or more keys |
| `EXISTS key` | 1 if key exists, 0 if not |
| `EXPIRE key seconds` | Set TTL on existing key |
| `TTL key` | Remaining TTL (-1 = no expiry, -2 = missing) |
| `KEYS *` | List all non-expired keys |
| `DBSIZE` | Number of keys in store |
| `INCR key` | Increment integer value by 1 |
| `APPEND key value` | Append string to existing value |
| `FLUSHALL` | Delete all keys |
| `MULTI` | Start transaction |
| `EXEC` | Execute queued transaction atomically |
| `DISCARD` | Discard transaction queue |
| `ECHO message` | Echo a message back |

---

## Benchmark Results

Measured on localhost (Windows, Python 3.13, RTX 3050 laptop):

| Benchmark | Ops/sec | Total ops | Time |
|---|---|---|---|
| SET (single client) | **21,026** | 10,000 | 475 ms |
| GET (single client) | **30,140** | 10,000 | 331 ms |
| INCR (single client) | **21,247** | 10,000 | 470 ms |
| Mixed SET+GET | **24,851** | 10,000 | 402 ms |
| **Concurrent (10 clients)** | **29,241** | 10,000 | 342 ms |

Run your own benchmark:
```bash
python benchmark.py --ops 10000 --clients 10
```

---

## Quick Start

### 1. Clone and install

```bash
git clone https://github.com/UtkarshKumarRai911/mini-redis.git
cd mini-redis
pip install -r requirements.txt
```

### 2. Start the server

```bash
python main.py
# [*] Mini-Redis listening on 127.0.0.1:6380
```

### 3. Connect with the CLI client

```bash
# Terminal 2
python client.py

mini-redis> SET name utkarsh
+OK
mini-redis> GET name
utkarsh
mini-redis> EXPIRE name 30
:1
mini-redis> TTL name
:28
```

### 4. Or connect with real redis-cli

```bash
redis-cli -p 6380
```

### 5. Test transactions

```
mini-redis> MULTI
+OK
mini-redis> SET city gwalior
+QUEUED
mini-redis> SET college iiitm
+QUEUED
mini-redis> EXEC
*2
+OK
+OK
mini-redis> GET city
gwalior
```

### 6. Test persistence

```bash
# Set some keys, stop the server (Ctrl+C), restart it
python main.py
# [AOF] Restored N commands from appendonly.aof
# Keys are still there
```

---

## Project Structure

```
mini-redis/
├── store/
│   └── store.py          # In-memory HashMap, TTL, LRU eviction (OOP + DSA)
├── protocol/
│   └── resp.py           # RESP wire protocol parser + encoder (CN)
├── persistence/
│   └── aof.py            # AOF Write-Ahead Log writer + loader (DBMS)
├── server/
│   ├── handler.py        # Command dispatcher (all 15 commands)
│   ├── session.py        # Per-client session + MULTI/EXEC transactions
│   └── tcp_server.py     # TCP socket server, thread-per-client (OS + CN)
├── tests/
│   ├── test_store.py     # 27 unit tests (GET/SET/TTL/LRU/concurrency)
│   └── test_protocol.py  # 15 unit tests (RESP encode/decode)
├── main.py               # Server entry point
├── client.py             # Interactive CLI client
├── benchmark.py          # Throughput benchmark (ops/sec)
└── requirements.txt
```

---

## Design Decisions

### Why one thread per client instead of async?
`threading.Thread` per connection demonstrates OS-level concurrency concepts directly — thread creation, mutex contention, and the GIL. An async approach (asyncio) would be faster in Python but hides the OS concepts this project is meant to demonstrate.

### Why OrderedDict for the store?
`OrderedDict` maintains insertion order and supports O(1) `move_to_end()` — perfect for LRU eviction. The least-recently-used key is always at the front; accessing a key moves it to the back.

### Why AOF instead of RDB snapshots?
AOF (Append-Only File) logs every write command — guaranteeing no data loss for any acknowledged write. RDB snapshots are faster but can lose the last N seconds of data. Redis itself defaults to AOF for durability.

### Why inner product for TTL?
TTL is stored as an absolute expiry epoch (`time.time() + seconds`). Checking expiry is a single float comparison — O(1). A min-heap would allow proactive expiry; this implementation uses lazy expiry (keys are cleaned up on access), which is exactly how Redis works.

---

## Running Tests

```bash
python -m pytest tests/ -v
```

```
42 passed in 3.42s
```

Test coverage includes:
- GET/SET/DEL/EXISTS correctness
- TTL expiry boundary conditions
- LRU eviction under capacity limit
- INCR on non-integer values (error handling)
- RESP protocol partial data (incomplete TCP packets)
- **Concurrent writes** — 100 threads incrementing the same counter

---

<p align="center">
  Built by <a href="https://github.com/UtkarshKumarRai911">Utkarsh Kumar Rai</a> · ABV-IIITM Gwalior · 2026
</p>
