#!/usr/bin/env python3
"""Prove WANT-GAP 8: chat-style and REPL-style boots share one Notus store."""
from __future__ import annotations

import json
import tempfile
import time
from pathlib import Path

from run_abin import (
    create_core_systems,
    shared_direct_notus_path,
    shutdown_core_systems,
)


def _memories(resp):
    content = resp.get("content") or {}
    return content.get("memories") or content.get("results") or []


def main() -> int:
    marker_a = f"WANTGAP8_PROVE_A_{int(time.time())}"
    marker_b = f"WANTGAP8_PROVE_B_{int(time.time())}"
    user = "matthew"
    shared = shared_direct_notus_path()
    print(f"shared_direct_notus_path={shared}")

    chat_rt = Path(tempfile.mkdtemp(prefix="monday-chat-prove-"))
    repl_rt = Path(tempfile.mkdtemp(prefix="monday-repl-prove-"))

    chat = create_core_systems(runtime_directory=str(chat_rt), enable_autonomous=False)
    print("chat_identity", json.dumps(chat["notus_identity"], default=str))
    assert chat["notus"].process_message(
        {
            "type": "store",
            "content": {
                "content": marker_a,
                "role": "user",
                "user_id": user,
                "memory_type": "conversation",
            },
        }
    ).get("status") == "success"
    shutdown_core_systems(chat)

    repl = create_core_systems(runtime_directory=str(repl_rt), enable_autonomous=False)
    print("repl_identity", json.dumps(repl["notus_identity"], default=str))
    q = repl["notus"].process_message(
        {"type": "query", "content": {"query": marker_a, "user_id": user, "limit": 20}}
    )
    hit = any(marker_a in str(m) for m in _memories(q))
    print(f"repl_sees_chat_write={hit}")
    if not hit:
        return 1
    assert repl["notus"].process_message(
        {
            "type": "store",
            "content": {
                "content": marker_b,
                "role": "user",
                "user_id": user,
                "memory_type": "conversation",
            },
        }
    ).get("status") == "success"
    shutdown_core_systems(repl)

    chat2 = create_core_systems(runtime_directory=str(chat_rt), enable_autonomous=False)
    q2 = chat2["notus"].process_message(
        {"type": "query", "content": {"query": marker_b, "user_id": user, "limit": 20}}
    )
    hit2 = any(marker_b in str(m) for m in _memories(q2))
    print(f"chat_sees_repl_write={hit2}")
    shutdown_core_systems(chat2)
    if not hit2:
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
