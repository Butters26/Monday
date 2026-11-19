#!/usr/bin/env python3
"""Persistent Mercy chat daemon for live talk.

Protocol over Unix socket ~/.local/state/mercy-chat/chat.sock:
  client sends one JSON line:
    {"text": "...", "user_id": "<who, or empty>"}       -> say something to her
    {"type": "poll", "user_id": "<who, or empty>"}     -> collect what she said on her own
  server replies one JSON line:
    said:  {"ok": true, "reply": "...", "unprompted": [...]}
    poll:  {"ok": true, "pending": ["..."]}
    error: {"ok": false, "error": "..."}
Also accepts text/line mode if first char is not '{'.

This is outside her: it hands what is typed to her senses and hears what she
says (outside_world.py). Her lobes do everything in between on their own.
Anything she says when nobody is waiting on a reply is kept for the next poll.

Memory: one shared Notus SQLite file at shared_direct_notus_path() (default
~/.local/state/mercy/notus_memory.sqlite3, override MERCY_NOTUS_SQLITE), the
same one run_abin uses. Sock/pid stay under MERCY_RUNTIME_DIR.
"""
from __future__ import annotations

import json
import os
import signal
import socket
import sys
import traceback
from pathlib import Path

from run_abin import (
    create_core_systems,
    describe_notus_identity,
    shutdown_core_systems,
)

RUNTIME = Path(os.environ.get("MERCY_RUNTIME_DIR", os.path.expanduser("~/.local/state/mercy-chat")))
SOCK_PATH = RUNTIME / "chat.sock"
PID_PATH = RUNTIME / "chat.pid"


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if SOCK_PATH.exists():
        SOCK_PATH.unlink()

    print(f"Booting Mercy core (runtime={RUNTIME})...", flush=True)
    # No notus_factory: open_primary_notus — same mind as run_abin REPL.
    systems = create_core_systems(
        runtime_directory=str(RUNTIME),
        enable_autonomous=True,
    )
    identity = systems.get("notus_identity") or describe_notus_identity(systems["notus"])
    print(
        "Notus live store: "
        f"backend={identity.get('backend')} role={identity.get('role')} "
        f"sqlite_path={identity.get('sqlite_path')}",
        flush=True,
    )
    PID_PATH.write_text(str(os.getpid()))

    outside = systems["outside"]
    stopping = {"v": False}

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCK_PATH))
    server.listen(8)
    SOCK_PATH.chmod(0o600)
    print(f"Mercy chat ready on {SOCK_PATH}", flush=True)

    def _stop(*_a):
        stopping["v"] = True
        try:
            server.close()
        except Exception:
            pass

    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    try:
        while not stopping["v"]:
            try:
                server.settimeout(1.0)
                try:
                    conn, _ = server.accept()
                except socket.timeout:
                    continue
            except OSError:
                break
            with conn:
                raw = b""
                while not raw.endswith(b"\n") and len(raw) < 1_000_000:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    conn.sendall(b'{"ok":false,"error":"empty"}\n')
                    continue
                try:
                    if line.startswith("{"):
                        req = json.loads(line)
                        req_type = str(req.get("type") or "").lower()
                        user_id = str(req.get("user_id") or "default")
                        if user_id == "default":
                            user_id = "unknown person 1"  # never assumed to be Matthew
                        if req_type == "poll":
                            conn.sendall(
                                (
                                    json.dumps(
                                        {"ok": True, "pending": outside.take_unprompted(user_id)},
                                        ensure_ascii=False,
                                    )
                                    + "\n"
                                ).encode()
                            )
                            continue
                        text = str(req.get("text") or "")
                    else:
                        text, user_id = line, "unknown person 1"
                    reply = outside.say(text, user_id=user_id)
                    unprompted = outside.take_unprompted(user_id)
                    conn.sendall(
                        (
                            json.dumps(
                                {
                                    "ok": True,
                                    "reply": reply,
                                    "unprompted": unprompted,
                                },
                                ensure_ascii=False,
                            )
                            + "\n"
                        ).encode()
                    )
                except Exception as e:
                    traceback.print_exc()
                    conn.sendall(
                        (json.dumps({"ok": False, "error": str(e)}) + "\n").encode()
                    )
    finally:
        stopping["v"] = True
        print("Shutting down Mercy...", flush=True)
        try:
            shutdown_core_systems(systems)
        except Exception:
            traceback.print_exc()
        for p in (SOCK_PATH, PID_PATH):
            try:
                p.unlink()
            except FileNotFoundError:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
