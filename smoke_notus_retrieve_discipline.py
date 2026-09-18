#!/usr/bin/env python3
"""Smoke: whole-history retrieve + empty-means-empty (not named test_*).

Stores several distinct facts across "time" (older buried under fillers),
asks about an older one (must find it), asks about unknown (must not invent).
Also checks contradict/update and the live chat path via Thalamus.
"""

from __future__ import annotations

import os
import sys
import uuid

os.environ.setdefault("NOTUS_POSTGRES_DB", "notus_memory")
os.environ.setdefault("NOTUS_POSTGRES_USER", os.getenv("USER", "box"))
os.environ.setdefault("NOTUS_POSTGRES_HOST", "localhost")
os.environ.setdefault("NOTUS_POSTGRES_PASSWORD", os.getenv("NOTUS_POSTGRES_PASSWORD", "box"))

from run_abin import create_core_systems, shutdown_core_systems


def main() -> int:
    systems = create_core_systems()
    th = systems["thalamus"]
    notus = systems["notus"]
    uid = f"smoke_retrieve_{uuid.uuid4().hex[:10]}"
    failures: list[str] = []

    # --- Time slice 1 (old): dog name ---
    th.process_user_input("Remember my dog is named Pixel.", user_id=uid)

    # Bury under chatter + newer unrelated facts (far past old ~50 window).
    for i in range(70):
        notus.store_memory(
            role="user",
            content=f"Filler chatter {i} about weather lunch traffic.",
            user_id=uid,
            importance=1.0,
        )

    # --- Time slice 2 (newer): color + job ---
    th.process_user_input("My favorite color is teal.", user_id=uid)
    th.process_user_input("I work as a carpenter.", user_id=uid)

    # --- Retrieve discipline (direct lobe) ---
    dog_mems = notus.retrieve_memories_smart("What is my dog's name?", user_id=uid, limit=10)
    dog_facts = notus.recall_facts("What is my dog's name?", user_id=uid, limit=10)
    dog_blob = "\n".join(
        [str(m.get("content", "")) for m in dog_mems]
        + [str(f.get("content") or f.get("text") or "") for f in dog_facts]
    )
    print("DOG retrieve memories=", len(dog_mems), "facts=", len(dog_facts))
    print("DOG blob ->", dog_blob[:400])

    if "Pixel" not in dog_blob:
        failures.append(f"old dog fact not found after burial: {dog_blob!r}")
    if any("teal" in str(x).lower() for x in [dog_blob]):
        # Unrelated newer color must not ride along for a dog-name query.
        # (strict: facts list should not contain favorite_color)
        if any(
            str(f.get("predicate", "")).lower().startswith("favorite")
            for f in dog_facts
        ):
            failures.append(f"dog query invented/recency-filled with color: {dog_facts!r}")

    unk_mems = notus.retrieve_memories_smart(
        "What is my spaceship serial number?", user_id=uid, limit=10
    )
    unk_facts = notus.recall_facts(
        "What is my spaceship serial number?", user_id=uid, limit=10
    )
    print("UNKNOWN memories=", len(unk_mems), "facts=", len(unk_facts))
    if unk_mems or unk_facts:
        failures.append(
            f"unknown query must be empty, got mems={unk_mems!r} facts={unk_facts!r}"
        )

    # Fragile extract must NOT store "my day is going well"
    before = notus.recall_facts("day going", user_id=uid, limit=20)
    learned = notus._ingest_personal_facts_from_text(
        "my day is going well", user_id=uid, source="smoke"
    )
    after = [
        f
        for f in notus.recall_facts("day", user_id=uid, limit=20)
        if str(f.get("predicate", "")).lower() == "day"
    ]
    print("fragile extract learned=", learned, "day facts=", after)
    if learned or after:
        failures.append(f"fragile extract too eager: learned={learned!r} after={after!r}")

    # Contradict/update: new dog name replaces old
    th.process_user_input("Remember my dog is named Rover.", user_id=uid)
    updated = notus.recall_facts("What is my dog's name?", user_id=uid, limit=10)
    objs = [str(f.get("object", "")) for f in updated]
    print("UPDATE facts objects=", objs)
    if "Rover" not in objs:
        failures.append(f"contradict/update missed Rover: {updated!r}")
    if "Pixel" in objs:
        failures.append(f"old contradicted Pixel still returned: {updated!r}")

    # --- Whole chat path ---
    ask = th.process_user_input("What is my dog's name?", user_id=uid)
    print("CHAT ask ->", ask)
    if "Rover" not in ask:
        failures.append(f"chat path failed to answer updated dog name: {ask!r}")
    if "How it felt" in ask:
        failures.append(f"chat path leaked poison: {ask!r}")

    unk_chat = th.process_user_input(
        "What is my spaceship serial number?", user_id=uid
    )
    print("CHAT unknown ->", unk_chat)
    # Must not answer with teal/carpenter/Rover as if it were the serial.
    low = (unk_chat or "").lower()
    if any(x in low for x in ("teal", "carpenter", "rover", "pixel")):
        failures.append(f"chat invented from unrelated recency: {unk_chat!r}")

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
