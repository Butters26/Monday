#!/usr/bin/env python3
"""Watch Mercy live: what is said to her, what every lobe does, and what she says.

It follows the tracer's file as she writes it, so you see it happen, not a
summary afterwards. It only reads; it changes nothing about her.

Use it next to her:
  window 1:  MERCY_TRACE=1 python _mercy_chat_daemon.py
  window 2:  python live_view.py            (or: python live_view.py <trace.jsonl>)
  window 3:  python _mercy_say.py "Hi Mercy"

Add --all to also see every message carried between lobes and every beat.
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path


def _trace_path(args: list) -> Path:
    named = [a for a in args if not a.startswith("--")]
    if named:
        return Path(named[0])
    configured = os.environ.get("MERCY_TRACE")
    if configured and configured not in ("1", "true", "yes"):
        return Path(configured)
    from runtime_paths import runtime_dir
    return runtime_dir() / "trace.jsonl"


def _clock(record: dict) -> str:
    try:
        return time.strftime("%H:%M:%S", time.localtime(float(record.get("ts")))) + \
            f".{int((float(record.get('ts')) % 1) * 1000):03d}"
    except Exception:
        return "--:--:--.---"


def _line(record: dict, everything: bool) -> str:
    """One trace record in plain words, or "" to leave it out."""
    kind = record.get("kind")
    r = record
    if kind == "boot":
        return f"MERCY BOOTED  lobes running on their own: {', '.join(r.get('running_on_own') or [])}"
    if kind == "turn_start":
        return f"\n>>> YOU SAID: {r.get('text')!r}"
    if kind == "turn_end":
        reply = r.get("reply") or ""
        if reply:
            return f"<<< MERCY SAID: {reply!r}   ({r.get('ms')} ms)"
        why = r.get("blank_cause") or "no reason recorded"
        return f"<<< MERCY SAID NOTHING   ({r.get('ms')} ms)   why: {why}" + \
            (f"\n    CRASHED: {r.get('error')}" if r.get("error") else "")
    if kind == "shared":
        what = ", ".join(r.get("what") or []) or "nothing"
        return f"    {r.get('from_lobe')} shared its take -> {len(r.get('to') or [])} lobes  [{what}]"
    if kind == "redid_take":
        return f"    {r.get('lobe')} redid its take (new from {r.get('because')})"
    if kind == "settled":
        return f"    --- she settled on the moment ---"
    if kind == "acted_on_settled":
        return f"    {r.get('lobe')} acted on its final take ({r.get('acts')} things done outside itself)"
    if kind == "waiting_for_signals":
        return f"    {r.get('lobe')} is WAITING for {', '.join(r.get('waiting_for') or [])}"
    if kind == "announce":
        heard = ", ".join(r.get("to") or []) or "nobody listening"
        return f"    {r.get('from')} announced {r.get('topic')!r} -> {heard}"
    if kind == "executive_bid":
        return f"    bid: {r.get('lobe')} -> {r.get('impulse')!r} (strength {round(float(r.get('strength') or 0), 3)})"
    if kind == "executive_decided":
        return f"    EXECUTIVE CONTROL chose {r.get('purpose')!r} (score {r.get('score')})"
    if kind == "reply_attempt":
        return f"    Language tried {r.get('sentence')!r}: " + ("OK" if r.get("ok") else f"sent back ({r.get('reason')})")
    if kind == "lobe_crashed":
        return f"!!! {r.get('lobe')} CRASHED on {r.get('msg_type')}: {r.get('error')}"
    if kind == "uncaught_error":
        return f"!!! UNCAUGHT ERROR in {r.get('where')}: {r.get('error')}"
    if kind in ("act_failed", "share_failed", "tell_failed"):
        return f"!!! {kind.replace('_', ' ').upper()}: {r.get('lobe')} {r.get('error') or r.get('message')}"
    if kind == "printed_warning":
        return f"    (printed) {r.get('line')}"
    if kind == "message" and r.get("outcome") in ("CRASHED", "NOT_UNDERSTOOD", "REJECTED", "NO_RECEIVER", "NO_ANSWER"):
        return f"!!! {r.get('from')} -> {r.get('to')} [{r.get('type')}] {r.get('outcome')}: {r.get('receiver_message')}"
    if everything:
        if kind == "message":
            return f"      {r.get('from')} -> {r.get('to')} [{r.get('type')}] {r.get('outcome')}"
        if kind == "state_shared":
            return f"      {r.get('from_lobe')} shared how it is right now"
        if kind == "handled" and r.get("msg_type") == "beat":
            return f"      beat: {r.get('lobe')}"
    return ""


def main(args: list) -> int:
    everything = "--all" in args
    path = _trace_path(args)
    print(f"Watching {path}  (Ctrl-C to stop)")
    while not path.exists():
        time.sleep(0.2)
    with path.open("r", encoding="utf-8") as fh:
        fh.seek(0, os.SEEK_END)  # from now on: what happens while you watch
        print("Live. Talk to her and it shows up here.\n")
        pending = ""
        while True:
            chunk = fh.readline()
            if not chunk:
                time.sleep(0.05)
                continue
            pending += chunk
            if not pending.endswith("\n"):
                continue
            line, pending = pending, ""
            try:
                record = json.loads(line)
            except json.JSONDecodeError:
                continue
            text = _line(record, everything)
            if text:
                print(f"{_clock(record)} {text}", flush=True)


if __name__ == "__main__":
    try:
        raise SystemExit(main(sys.argv[1:]))
    except KeyboardInterrupt:
        pass
