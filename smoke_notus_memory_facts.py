#!/usr/bin/env python3
"""Smoke: remember dog name, recall it, greeting gate must not blank check-ins."""

from __future__ import annotations

import os
import sys

os.environ.setdefault("NOTUS_POSTGRES_DB", "notus_memory")
os.environ.setdefault("NOTUS_POSTGRES_USER", os.getenv("USER", "box"))
os.environ.setdefault("NOTUS_POSTGRES_HOST", "localhost")

from run_abin import create_core_systems, shutdown_core_systems


def main() -> int:
    systems = create_core_systems()
    th = systems["thalamus"]
    notus = systems["notus"]
    uid = "smoke_notus_memory_facts"
    failures = []

    remember = th.process_user_input("Remember my dog is named Pixel.", user_id=uid)
    ask = th.process_user_input("What is my dog's name?", user_id=uid)
    checkin = th.process_user_input("hey, are you okay?", user_id=uid)

    print("Remember ->", remember)
    print("Ask      ->", ask)
    print("Check-in ->", checkin)

    if "Pixel" not in ask or "How it felt" in ask:
        failures.append(f"dog-name recall failed: {ask!r}")
    if "Got it" not in remember and "Pixel" not in remember:
        failures.append(f"teaching ack weak: {remember!r}")
    if "How it felt" in checkin or "dog_name" in checkin:
        failures.append(f"check-in returned poison/fact dump: {checkin!r}")

    gate_hi = len(notus.retrieve_memories_smart("hi", user_id=uid, limit=5))
    # Check-in must not be classified as a greeting (may still be empty if nothing
    # relevant — empty means empty). Pure "hi" stays blanked.
    checkin_is_greeting = notus._simple_greeting("hey, are you okay?")
    gate_check = len(notus.retrieve_memories_smart("hey, are you okay?", user_id=uid, limit=5))
    print(
        "gate hi count=", gate_hi,
        "check-in greeting?", checkin_is_greeting,
        "check-in count=", gate_check,
    )
    if gate_hi != 0:
        failures.append("simple 'hi' should still skip retrieval")
    if checkin_is_greeting:
        failures.append("check-in must not be blanked by greeting gate")

    shutdown_core_systems(systems)
    if failures:
        print("FAIL:")
        for f in failures:
            print(" -", f)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
