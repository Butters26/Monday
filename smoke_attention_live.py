#!/usr/bin/env python3
"""Pass/fail smoke: attention on the live path.

Proves:
  (1) create_core_systems registers attention
  (2) process_message evaluate handles real competing signals
  (3) salience ranks (urgent/user > ambient)
  (4) decay lowers stored scores
  (5) live chat path still works and actually hits attention

No test_*.py. No cloud. No percents. PASS/FAIL only.
Run: python3 smoke_attention_live.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import List, Tuple

os.environ.setdefault("NOTUS_POSTGRES_DB", "notus_memory")
os.environ.setdefault("NOTUS_POSTGRES_USER", os.getenv("USER", "box"))
os.environ.setdefault("NOTUS_POSTGRES_HOST", "localhost")
os.environ.setdefault(
    "NOTUS_POSTGRES_PASSWORD", os.getenv("NOTUS_POSTGRES_PASSWORD", "box")
)

from attention_lobe import AttentionLobe
from run_abin import create_core_systems, shutdown_core_systems


def main() -> int:
    runtime = Path(tempfile.mkdtemp(prefix="monday-attention-smoke-"))
    results: List[Tuple[str, str, str]] = []

    def mark(case: str, ok: bool, detail: str = "") -> None:
        results.append((case, "PASS" if ok else "FAIL", detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {case}" + (f" — {detail}" if detail else ""))

    print("=== smoke_attention_live ===")
    print(f"runtime: {runtime}")

    systems = None
    try:
        systems = create_core_systems(runtime_directory=str(runtime))
        mark("create_core_systems", True)
    except Exception as exc:
        mark("create_core_systems", False, f"CRASH: {exc}")
        traceback.print_exc()
        for case, status, detail in results:
            print(f"{status}: {case}" + (f" — {detail}" if detail else ""))
        return 1

    th = systems["thalamus"]
    attention = systems.get("attention")

    registered = "attention" in th.lobe_handlers and isinstance(attention, AttentionLobe)
    mark("attention registered", registered)

    # --- Direct process_message: competing signals ---
    try:
        resp = th.send_and_wait(
            "attention",
            "evaluate",
            {
                "signals": [
                    {
                        "id": "ambient",
                        "text": "ambient room tone",
                        "source": "ambient",
                        "priority": 0.0,
                    },
                    {
                        "id": "urgent_help",
                        "text": "I need urgent help, this is important",
                        "source": "user",
                        "priority": 0.6,
                        "emotions": ["worried"],
                    },
                    {
                        "id": "mild_hi",
                        "text": "hi",
                        "source": "user",
                        "priority": 0.1,
                    },
                ]
            },
            source="smoke",
        )
        ok = resp.get("status") == "success"
        body = resp.get("content") if isinstance(resp.get("content"), dict) else {}
        ranked = body.get("ranked") or resp.get("ranked") or []
        focus = body.get("focus") or resp.get("focus")
        mark(
            "process_message evaluate",
            ok and bool(ranked),
            f"focus={focus!r} n={len(ranked)}" if ok else str(resp.get("message")),
        )
        # Salience ranks: urgent must beat ambient
        scores = {r["id"]: float(r["score"]) for r in ranked if isinstance(r, dict) and "id" in r}
        rank_ok = (
            "urgent_help" in scores
            and "ambient" in scores
            and scores["urgent_help"] > scores["ambient"]
            and focus == "urgent_help"
        )
        mark(
            "salience ranks urgent > ambient",
            rank_ok,
            f"scores={scores} focus={focus!r}",
        )
    except Exception as exc:
        mark("process_message evaluate", False, f"CRASH: {exc}")
        mark("salience ranks urgent > ambient", False, "skipped")
        traceback.print_exc()

    # --- Decay ---
    try:
        before = dict(attention.salience_map)
        if not before:
            # Seed if evaluate somehow cleared
            attention.update_salience(
                [{"id": "seed", "text": "important seed", "source": "user", "priority": 0.8}]
            )
            before = dict(attention.salience_map)
        decay_resp = th.send_and_wait("attention", "decay", {}, source="smoke")
        after = dict(attention.salience_map)
        lowered = False
        for sid, score in before.items():
            if sid in after and after[sid] < score:
                lowered = True
                break
            if sid not in after and score >= attention.min_salience:
                # Dropped below min counts as decay working
                lowered = True
                break
        # Also accept: all scores multiplied down even if same keys
        if not lowered and before and after:
            lowered = all(
                after.get(sid, 0.0) <= score * (1.0 - attention.decay_rate + 1e-9)
                for sid, score in before.items()
                if sid in after
            )
        mark(
            "decay lowers scores",
            decay_resp.get("status") == "success" and lowered,
            f"before={before} after={after}",
        )
    except Exception as exc:
        mark("decay lowers scores", False, f"CRASH: {exc}")
        traceback.print_exc()

    # --- Live chat path ---
    user_id = f"attn-smoke-{uuid.uuid4().hex[:8]}"
    try:
        # Reset attention so live turn is clean
        attention.reset()
        routes_before = len(th.message_routes)
        reply = th.process_user_input(
            "Why is this important emergency help needed?",
            user_id=user_id,
        )
        chat_ok = isinstance(reply, str) and bool(reply.strip()) and "trouble" not in reply.lower()[:40]
        # Did attention get hit on the live path?
        routes = list(th.message_routes)[routes_before:]
        hit_evaluate = any(
            r.get("to") == "attention" and r.get("type") == "evaluate" and r.get("status") == "success"
            for r in routes
        )
        mark(
            "live chat path works",
            chat_ok,
            f"reply_len={len(reply) if isinstance(reply, str) else 0}",
        )
        mark(
            "live path hits attention evaluate",
            hit_evaluate,
            f"attention_routes={[r for r in routes if r.get('to')=='attention']}",
        )
        # Focus should prefer user_input over ambient after live evaluate
        status = th.send_and_wait("attention", "get_status", {}, source="smoke")
        body = status.get("content") if isinstance(status.get("content"), dict) else {}
        focus = body.get("current_focus") or attention.current_focus
        live_focus_ok = isinstance(focus, str) and focus != "ambient_noise" and bool(focus)
        mark(
            "live focus not ambient",
            live_focus_ok,
            f"focus={focus!r}",
        )
    except Exception as exc:
        mark("live chat path works", False, f"CRASH: {exc}")
        mark("live path hits attention evaluate", False, "skipped")
        mark("live focus not ambient", False, "skipped")
        traceback.print_exc()

    try:
        shutdown_core_systems(systems)
    except Exception:
        traceback.print_exc()

    print("---")
    failed = [r for r in results if r[1] == "FAIL"]
    for case, status, detail in results:
        print(f"{status}: {case}" + (f" — {detail}" if detail else ""))
    if failed:
        print(f"RESULT: FAIL ({len(failed)} failed)")
        return 1
    print("RESULT: PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
