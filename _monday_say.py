#!/usr/bin/env python3
"""Send one line to the Monday chat daemon and print her reply.

Usage:
  _monday_say.py <message>          # prompted turn
  _monday_say.py --poll [user_id]   # drain unprompted pending
"""
from __future__ import annotations

import json
import os
import socket
import sys
from pathlib import Path

SOCK = Path(os.environ.get("MONDAY_RUNTIME_DIR", os.path.expanduser("~/.local/state/monday-chat"))) / "chat.sock"


def _request(payload: dict) -> dict:
    if not SOCK.exists():
        raise SystemExit(f"Monday chat daemon not running (no {SOCK})")
    s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    s.connect(str(SOCK))
    s.sendall((json.dumps(payload) + "\n").encode())
    buf = b""
    while not buf.endswith(b"\n"):
        chunk = s.recv(4096)
        if not chunk:
            break
        buf += chunk
    s.close()
    data = json.loads(buf.decode() or "{}")
    if not data.get("ok"):
        raise SystemExit(data.get("error") or "Monday error")
    return data


def say(text: str, user_id: str = "matthew") -> str:
    data = _request({"text": text, "user_id": user_id})
    for u in data.get("unprompted") or []:
        if isinstance(u, str) and u.strip():
            print(f"[unprompted] {u}")
    return data["reply"]


def poll(user_id: str = "matthew") -> list:
    data = _request({"type": "poll", "user_id": user_id})
    return list(data.get("pending") or [])


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] in ("--poll", "-p"):
        uid = args[1] if len(args) > 1 else "matthew"
        for item in poll(uid):
            print(item)
        raise SystemExit(0)
    msg = " ".join(args).strip() or sys.stdin.read().strip()
    if not msg:
        raise SystemExit("usage: _monday_say.py <message> | --poll [user_id]")
    print(say(msg))
