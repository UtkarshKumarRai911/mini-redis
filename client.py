"""
client.py — Simple interactive CLI client for Mini-Redis.

CN concept: client-side TCP socket connecting to the server.
Sends inline commands (plain text), reads RESP responses.

Usage:
    python client.py
    python client.py --host 127.0.0.1 --port 6380
"""

import socket
import argparse


def send_command(sock: socket.socket, command: str) -> str:
    """Send a command string and read the full response."""
    sock.sendall((command.strip() + "\r\n").encode())
    response = b""
    while True:
        chunk = sock.recv(4096)
        response += chunk
        if len(chunk) < 4096:
            break
    return response.decode(errors="replace").strip()


def main():
    parser = argparse.ArgumentParser(description="Mini-Redis CLI client")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=6380)
    args = parser.parse_args()

    print(f"Connecting to Mini-Redis at {args.host}:{args.port}...")
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((args.host, args.port))
        sock.settimeout(2.0)
    except ConnectionRefusedError:
        print("ERROR: Could not connect. Is the server running?")
        print("Start it with: python main.py")
        return

    print(f"Connected. Type commands (PING, SET k v, GET k, DEL k, QUIT)\n")

    while True:
        try:
            cmd = input("mini-redis> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBye!")
            break

        if not cmd:
            continue
        if cmd.upper() == "QUIT":
            print("Bye!")
            break

        try:
            response = send_command(sock, cmd)
            print(response)
        except socket.timeout:
            print("(no response — timeout)")
        except Exception as e:
            print(f"ERROR: {e}")
            break

    sock.close()


if __name__ == "__main__":
    main()
