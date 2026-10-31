#!/usr/bin/env python3
"""Summarize a live trace written by trace_monitor.py.

Usage: python trace_report.py [trace.jsonl]   (default: <runtime dir>/trace.jsonl)
"""

from __future__ import annotations

import collections
import json
import sys
from pathlib import Path

PROBLEM_OUTCOMES = ("CRASHED", "NOT_UNDERSTOOD", "REJECTED", "NO_RECEIVER", "NO_ANSWER")


def load(path: str):
    records = []
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            records.append({"kind": "unreadable_line", "line": line[:200]})
    return records


def main() -> int:
    if len(sys.argv) > 1:
        path = sys.argv[1]
    else:
        from runtime_paths import runtime_dir
        path = str(runtime_dir() / "trace.jsonl")
    records = load(path)
    by_kind = collections.Counter(r.get("kind") for r in records)
    messages = [r for r in records if r.get("kind") == "message"]
    turns = [r for r in records if r.get("kind") == "turn_end"]
    starts = {r["turn"]: r for r in records if r.get("kind") == "turn_start"}

    print(f"Trace: {path}")
    print(f"Boots: {by_kind.get('boot', 0)}   turns: {len(turns)}   messages: {len(messages)}")

    print("\n== CONVERSATION ==")
    for t in turns:
        said = starts.get(t["turn"], {}).get("text", "?")
        reply = t.get("reply") or ""
        note = ""
        if t.get("blank"):
            note = f"   [BLANK: {t.get('blank_cause')}]"
        if t.get("error"):
            note += "   [CRASHED]"
        print(f"you: {said}\nher: {reply!r}{note}   ({t.get('ms')} ms)")

    print("\n== PROBLEMS ==")
    problems = collections.Counter(
        (r.get("from"), r.get("to"), r.get("type"), r.get("outcome"), (r.get("receiver_message") or "")[:90])
        for r in messages if r.get("outcome") in PROBLEM_OUTCOMES)
    if not problems:
        print("no failed messages")
    for (src, dst, typ, outcome, msg), n in problems.most_common():
        print(f"{n:4d}  {outcome:14s} {src} -> {dst} [{typ}]  {msg}")

    boots = [r for r in records if r.get("kind") == "boot"]
    if boots and "running_on_own" in boots[-1]:
        b = boots[-1]
        print(f"\n== LOBES RUNNING ON THEIR OWN: {len(b.get('running_on_own') or [])} ==")
        if b.get("not_running_on_own"):
            print(f"  NOT running on their own: {', '.join(b['not_running_on_own'])}")

    announces = collections.Counter(
        (r.get("from"), r.get("topic"), ", ".join(r.get("to") or []) or "nobody listening")
        for r in records if r.get("kind") == "announce")
    if announces:
        print("\n== ANNOUNCEMENTS (who announced what, who heard it) ==")
        for (src, topic, heard), n in sorted(announces.items()):
            print(f"{n:4d}  {src} announced {topic!r} -> {heard}")

    failed_tells = collections.Counter(
        (r.get("lobe"), r.get("msg_type"), (r.get("message") or "")[:90])
        for r in records if r.get("kind") == "tell_failed")
    if failed_tells:
        print("\n== ANNOUNCEMENTS / TELLS A LOBE FAILED TO HANDLE ==")
        for (lobe, typ, msg), n in failed_tells.most_common():
            print(f"{n:4d}  {lobe} [{typ}]  {msg}")

    crashes = [r for r in records if r.get("kind") == "lobe_crashed"]
    if crashes:
        print(f"\n== LOBE CRASHES: {len(crashes)} (where, from the traceback) ==")
        seen = set()
        for r in crashes:
            key = (r.get("lobe"), r.get("msg_type"), r.get("error"))
            if key in seen:
                continue
            seen.add(key)
            n = sum(1 for c in crashes if (c.get("lobe"), c.get("msg_type"), c.get("error")) == key)
            print(f"-- {n}x {r.get('lobe')} [{r.get('msg_type')}] {r.get('error')}")
            print("   " + "\n   ".join((r.get("traceback") or "").strip().splitlines()[-8:]))

    errors = [r for r in records if r.get("kind") == "uncaught_error"]
    print(f"\n== UNCAUGHT ERRORS: {len(errors)} ==")
    for r in errors:
        print(f"-- {r.get('where')}\n{r.get('error')}")

    crashed_turns = [t for t in turns if t.get("error")]
    print(f"\n== CRASHED TURNS: {len(crashed_turns)} ==")
    for t in crashed_turns:
        print(t.get("error"))

    blanks = collections.Counter(t.get("blank_cause") for t in turns if t.get("blank"))
    print(f"\n== BLANK REPLIES: {sum(blanks.values())} ==")
    for cause, n in blanks.most_common():
        print(f"{n:4d}  {cause}")

    printed = collections.Counter(r.get("line") for r in records if r.get("kind") == "printed_warning")
    print(f"\n== PRINTED WARNINGS: {sum(printed.values())} ==")
    for line, n in printed.most_common(15):
        print(f"{n:4d}  {line}")

    attempts = [r for r in records if r.get("kind") == "reply_attempt"]
    if attempts:
        rejected = [r for r in attempts if not r.get("ok")]
        print(f"\n== REPLY ATTEMPTS: {len(attempts)} (rejected by reasoning: {len(rejected)}) ==")
        for r in rejected[-15:]:
            print(f"  rejected: {r.get('sentence')!r}  because {r.get('reason')}")

    unsigned = sum(1 for r in messages if r.get("claimed_from") == "thalamus"
                   and not str(r.get("from", "")).startswith("thalamus") and r.get("from") != "unknown")
    print(f"\nUnsigned lobe messages (claimed to be thalamus): {unsigned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
