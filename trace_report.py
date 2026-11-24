#!/usr/bin/env python3
"""Summarize a live trace written by trace_monitor.py.

Usage: python trace_report.py [trace.jsonl]   (default: <runtime dir>/trace.jsonl)
"""

from __future__ import annotations

import collections
import json
import sys
from typing import Dict
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

    shared = [r for r in records if r.get("kind") == "shared"]
    waited = [r for r in records if r.get("kind") == "waiting_for_signals"]
    share_failed = [r for r in records if r.get("kind") == "share_failed"]
    if shared or waited or share_failed:
        print("\n== SIGNALS (each lobe fires what it made of a moment to all the others; nobody asks) ==")
        by_moment: Dict[str, list] = collections.OrderedDict()
        for r in shared:
            by_moment.setdefault(r.get("moment"), []).append(r.get("from_lobe"))
        for moment, order in by_moment.items():
            print(f"  {moment}: fired in this order: {', '.join(str(o) for o in order)}")
        fired = {(r.get("from_lobe"), r.get("moment")) for r in shared}
        empty = collections.Counter(r.get("from_lobe") for r in shared if r.get("empty"))
        for lobe, n in empty.most_common():
            print(f"{n:4d}  {lobe} fired nothing about a moment")
        for r in waited:
            if (r.get("lobe"), r.get("moment")) not in fired:
                print(f"  NEVER FIRED: {r.get('lobe')} on {r.get('moment')} "
                      f"(was waiting for {', '.join(r.get('waiting_for') or [])})")
        for r in share_failed:
            print(f"  FIRING FAILED: {r.get('lobe')} on {r.get('moment')}: {r.get('error')}")

    volumes = [r for r in records if r.get("kind") == "thalamus_volume"]
    ahead = collections.Counter((r.get("lobe"), r.get("sender"), r.get("msg_type"))
                                for r in records if r.get("kind") == "thalamus_priority")
    unlocked = collections.Counter((r.get("lobe"), r.get("for_lobe"), r.get("served"))
                                   for r in records if r.get("kind") == "thalamus_unlocked")
    refused = collections.Counter(r.get("asked_by") for r in records if r.get("kind") == "thalamus_volume_refused")
    print("\n== THALAMUS (besides carrying) ==")
    print(f"volume set by Attention: {len(volumes)} times"
          + (f"; last: {volumes[-1].get('levels')}" if volumes else ""))
    for who, n in refused.most_common():
        print(f"{n:4d}  volume change REFUSED: asked by {who} (only Attention sets it)")
    for (lobe, sender, typ), n in ahead.most_common():
        print(f"{n:4d}  went first because it was louder: {sender} -> {lobe} [{typ}]")
    for (lobe, other, typ), n in unlocked.most_common():
        print(f"{n:4d}  un-stuck: {lobe} and {other} were waiting on each other; {lobe} answered [{typ}] first")

    thoughts = [r for r in records if r.get("kind") == "thought"]
    no_thoughts = collections.Counter(r.get("reason") for r in records if r.get("kind") == "thought_none")
    if thoughts or no_thoughts:
        print(f"\n== HER OWN THOUGHTS (nobody asked): {len(thoughts)} ==")
        for r in thoughts:
            print(f"  about {r.get('about')!r}   (started from {r.get('started_from')}; {r.get('ms')} ms)")
            print(f"    Notus brought with it: {r.get('with_memories') or 'nothing'}")
            print(f"    Reasoning: knows {r.get('knows') or 'nothing'}; follows {r.get('follows') or 'nothing'}"
                  + (f"; problem {r.get('problem')}" if r.get("problem") else "")
                  + (f"; unsure: {r.get('unsure')}" if r.get("unsure") else ""))
            print(f"    leads on to: {r.get('leads_to') or 'nowhere'}")
        for reason, n in no_thoughts.most_common():
            print(f"{n:4d}  no thought: {reason}")

    focus = [r for r in records if r.get("kind") == "attention_focus"]
    if focus:
        print(f"\n== ATTENTION: {len(focus)} times her focus was weighed ==")
        for r in focus:
            others = ", ".join(f"{c.get('id')} {c.get('score')}" for c in r.get("competing") or [])
            print(f"  focus: {r.get('focus')} ({r.get('score')}) on {r.get('on')!r} after {r.get('because')}; competing: {others}")

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

    executive = [r for r in records if str(r.get("kind") or "").startswith("executive_")]
    if executive:
        print(f"\n== EXECUTIVE CONTROL: {len(executive)} events ==")
        for r in executive:
            kind = r["kind"][len("executive_"):]
            if kind == "bid":
                print(f"    bid: {r.get('lobe')} -> {r.get('impulse')!r} (strength {r.get('strength')}, {r.get('channel')}) "
                      f"because {r.get('why')}")
            elif kind == "decided":
                print(f"  decided: {r.get('purpose')!r} because {r.get('situation')!r} "
                      f"(score {r.get('score')}, weighed {r.get('weighed')}) about {r.get('about')!r}; "
                      f"steps {r.get('steps')}; other options {r.get('others')}")
            elif kind == "step":
                print(f"    step {r.get('step')!r}: {r.get('status')} - {r.get('result')}")
            elif kind == "monitored":
                print(f"    result: {r.get('status')}; failed {r.get('failed')}; waiting {r.get('waiting')}")
            elif kind in ("switched", "kept", "resumed"):
                print(f"  {kind}: " + ", ".join(f"{k}={v!r}" for k, v in r.items()
                                               if k not in ("kind", "ts", "turn", "thread")))
            elif kind in ("held_back", "allowed", "chose"):
                print(f"  {kind}: {r.get('action')!r} from {r.get('source')!r}: {r.get('reason')}")
            else:
                print(f"  {kind}: " + ", ".join(f"{k}={v!r}" for k, v in r.items()
                                               if k not in ("kind", "ts", "turn", "thread")))

    unsigned = sum(1 for r in messages if r.get("claimed_from") == "thalamus"
                   and not str(r.get("from", "")).startswith("thalamus") and r.get("from") != "unknown")
    print(f"\nUnsigned lobe messages (claimed to be thalamus): {unsigned}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
