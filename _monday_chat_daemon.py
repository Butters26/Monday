#!/usr/bin/env python3
"""Persistent Monday chat daemon for live talk (direct-call core).

Protocol over Unix socket ~/.local/state/monday-chat/chat.sock:
  client sends one JSON line:
    {"text": "...", "user_id": "matthew"}                 → prompted turn
    {"type": "poll", "user_id": "matthew"}               → drain unprompted pending
    {"type": "deliver_unprompted", "user_id": "matthew",
     "force": {...}}                                     → operator/smoke deliver
  server replies one JSON line:
    prompted: {"ok": true, "reply": "...", "unprompted": [...]}
    poll:     {"ok": true, "pending": ["..."]}
    deliver:  {"ok": true, "spoke": bool, "text": ..., "reason": ...}
    error:    {"ok": false, "error": "..."}
Also accepts text/line mode if first char is not '{'.

Background thread (~8–15s) calls Thalamus.deliver_unprompted_speech for active
users so Monday can speak without a user turn. Speech stays decision-only;
delivery is Thalamus→Output (+ this pending/poll push).

Notus identity (WANT-GAP 8): same path as create_core_systems / run_abin —
PostgreSQL ActiveNotus when reachable; otherwise one shared DirectNotus file
at shared_direct_notus_path() (default ~/.local/state/monday/notus_memory.sqlite3,
override MONDAY_NOTUS_SQLITE). Sock/pid stay under MONDAY_RUNTIME_DIR
(default ~/.local/state/monday-chat); memory is NOT a separate chat DB.
Issue #11 Thalamus.notus_fallback still covers mid-turn store/query outages.
Not Learning; not cloud.
"""
from __future__ import annotations

import json
import os
import random
import signal
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

from run_abin import (
    create_core_systems,
    describe_notus_identity,
    shutdown_core_systems,
)

RUNTIME = Path(os.environ.get("MONDAY_RUNTIME_DIR", os.path.expanduser("~/.local/state/monday-chat")))
SOCK_PATH = RUNTIME / "chat.sock"
PID_PATH = RUNTIME / "chat.pid"

ACTIVE_USERS = ("matthew",)


def main() -> int:
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if SOCK_PATH.exists():
        SOCK_PATH.unlink()

    print(f"Booting Monday core (runtime={RUNTIME})...", flush=True)
    # No notus_factory: open_primary_notus — same mind as run_abin REPL.
    systems = create_core_systems(
        runtime_directory=str(RUNTIME),
        enable_autonomous=True,
    )
    thalamus = systems["thalamus"]
    identity = systems.get("notus_identity") or describe_notus_identity(systems["notus"])
    print(
        "Notus live store: "
        f"backend={identity.get('backend')} role={identity.get('role')} "
        f"sqlite_path={identity.get('sqlite_path')}",
        flush=True,
    )
    if identity.get("postgres_error"):
        print(f"Notus Postgres probe: {identity['postgres_error']}", flush=True)
    PID_PATH.write_text(str(os.getpid()))

    pending_lock = threading.Lock()
    pending: dict[str, list[str]] = {u: [] for u in ACTIVE_USERS}
    stopping = {"v": False}

    def _drain(user_id: str) -> list[str]:
        with pending_lock:
            items = list(pending.get(user_id) or [])
            pending[user_id] = []
            return items

    def _append_pending(user_id: str, text: str) -> None:
        with pending_lock:
            bucket = pending.setdefault(user_id, [])
            bucket.append(text)
            if len(bucket) > 32:
                del bucket[:-32]

    def _force_inject(force: dict) -> None:
        from autonomous_thinking import AutonomousThought

        auto = systems.get("autonomous")
        if auto is None:
            return
        content = str(force.get("content") or "").strip()
        if not content:
            return
        if force.get("reset_cooldown"):
            thalamus._last_spoken_aside_time = 0.0
            sp = systems.get("speech")
            if sp is not None:
                sp.last_speech_time = 0.0
                sp.conversation_active = False
                sp.user_is_typing = False
                sp.user_is_busy = False
        thought = AutonomousThought(
            id=f"op_force_{int(time.time() * 1000)}",
            content=content,
            thought_type=str(force.get("thought_type") or "feeling"),
            trigger=str(force.get("trigger") or "unresolved_operator"),
            intensity=float(force.get("intensity") or 0.9),
            speak_worthy=True,
            timestamp=time.time(),
            mode="inner",
            topic_key=str(force.get("topic_key") or ""),
        )
        lock = getattr(auto, "lock", None)
        if lock is not None:
            with lock:
                auto.thought_queue.insert(0, thought)
        else:
            auto.thought_queue.insert(0, thought)

    def _unprompted_loop() -> None:
        while not stopping["v"]:
            delay = random.uniform(8.0, 15.0)
            end = delay
            while end > 0 and not stopping["v"]:
                step = min(0.5, end)
                time.sleep(step)
                end -= step
            if stopping["v"]:
                break
            for user_id in ACTIVE_USERS:
                if stopping["v"]:
                    break
                try:
                    result = thalamus.deliver_unprompted_speech(user_id=user_id)
                except Exception:
                    traceback.print_exc()
                    continue
                if not isinstance(result, dict):
                    continue
                if result.get("spoke") and isinstance(result.get("text"), str):
                    text = result["text"].strip()
                    if text:
                        _append_pending(user_id, text)
                        print(f"[unprompted] {user_id}: {text[:120]}", flush=True)

    bg = threading.Thread(target=_unprompted_loop, name="unprompted-speech", daemon=True)
    bg.start()

    server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    server.bind(str(SOCK_PATH))
    server.listen(8)
    SOCK_PATH.chmod(0o600)
    print(f"Monday chat ready on {SOCK_PATH}", flush=True)

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
                        user_id = str(req.get("user_id") or "matthew")
                        if req_type == "poll":
                            drained = _drain(user_id)
                            conn.sendall(
                                (
                                    json.dumps(
                                        {"ok": True, "pending": drained},
                                        ensure_ascii=False,
                                    )
                                    + "\n"
                                ).encode()
                            )
                            continue
                        if req_type == "deliver_unprompted":
                            force = req.get("force")
                            if isinstance(force, dict):
                                try:
                                    _force_inject(force)
                                except Exception:
                                    traceback.print_exc()
                            result = thalamus.deliver_unprompted_speech(user_id=user_id)
                            if not isinstance(result, dict):
                                result = {
                                    "spoke": False,
                                    "text": None,
                                    "reason": "bad_result",
                                }
                            if (
                                result.get("spoke")
                                and isinstance(result.get("text"), str)
                                and result["text"].strip()
                            ):
                                _append_pending(user_id, result["text"].strip())
                            conn.sendall(
                                (
                                    json.dumps({"ok": True, **result}, ensure_ascii=False)
                                    + "\n"
                                ).encode()
                            )
                            continue
                        text = str(req.get("text") or "")
                    else:
                        text, user_id = line, "matthew"
                    reply = thalamus.process_user_input(text, user_id=user_id)
                    unprompted = _drain(user_id)
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
        print("Shutting down Monday...", flush=True)
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
