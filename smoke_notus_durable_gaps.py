#!/usr/bin/env python3
"""Smoke: durable fact breadth + retrieve ranking (not named test_*).

(a) codeword / arbitrary durable fact taught, found under filler burial
(b) dog name still found under filler
(c) unknown stays empty / honest
(d) Monday speech still stored and retrievable
(e) fragile chatter still skipped; contradict/update still works
"""

from __future__ import annotations

import os
import uuid

os.environ.setdefault("NOTUS_POSTGRES_DB", "notus_memory")
os.environ.setdefault("NOTUS_POSTGRES_USER", os.getenv("USER", "box"))
os.environ.setdefault("NOTUS_POSTGRES_HOST", "localhost")
os.environ.setdefault(
    "NOTUS_POSTGRES_PASSWORD", os.getenv("NOTUS_POSTGRES_PASSWORD", "box")
)

from run_abin import create_core_systems, shutdown_core_systems


def _blob(mems, facts) -> str:
    parts = [str(m.get("content", "")) for m in mems]
    for f in facts:
        parts.append(
            str(f.get("content") or f.get("text") or f.get("object") or "")
        )
        parts.append(str(f.get("predicate") or ""))
    return "\n".join(parts)


def main() -> int:
    systems = create_core_systems()
    th = systems["thalamus"]
    notus = systems["notus"]
    uid = f"smoke_gaps_{uuid.uuid4().hex[:10]}"
    failures: list[str] = []

    # --- (a) codeword + arbitrary durable under filler ---
    th.process_user_input(
        "Remember the codeword is NebulaQuartz.", user_id=uid
    )
    th.process_user_input(
        "Remember the project name is Aurora.", user_id=uid
    )
    for i in range(70):
        notus.store_memory(
            role="user",
            content=f"Filler chatter {i} about weather lunch traffic.",
            user_id=uid,
            importance=1.0,
        )

    cw_mems = notus.retrieve_memories_smart(
        "What is the codeword?", user_id=uid, limit=10
    )
    cw_facts = notus.recall_facts("What is the codeword?", user_id=uid, limit=10)
    cw_blob = _blob(cw_mems, cw_facts)
    print("A codeword blob ->", cw_blob[:400])
    if "NebulaQuartz" not in cw_blob:
        failures.append(f"(a) codeword not found under filler: {cw_blob!r}")

    proj_facts = notus.recall_facts(
        "What is the project name?", user_id=uid, limit=10
    )
    proj_blob = _blob([], proj_facts)
    print("A project facts ->", proj_blob[:300])
    if "Aurora" not in proj_blob:
        failures.append(f"(a) project name fact missing: {proj_facts!r}")

    # --- (b) dog name under filler (Pixel -> later Rover update below) ---
    th.process_user_input("Remember my dog is named Pixel.", user_id=uid)
    for i in range(40):
        notus.store_memory(
            role="user",
            content=f"More filler {i} about groceries and podcasts.",
            user_id=uid,
            importance=1.0,
        )
    dog_mems = notus.retrieve_memories_smart(
        "What is my dog's name?", user_id=uid, limit=10
    )
    dog_facts = notus.recall_facts("What is my dog's name?", user_id=uid, limit=10)
    dog_blob = _blob(dog_mems, dog_facts)
    print("B dog blob ->", dog_blob[:400])
    if "Pixel" not in dog_blob:
        failures.append(f"(b) dog name not found under filler: {dog_blob!r}")

    # --- (c) unknown empty ---
    unk_mems = notus.retrieve_memories_smart(
        "What is my spaceship serial number?", user_id=uid, limit=10
    )
    unk_facts = notus.recall_facts(
        "What is my spaceship serial number?", user_id=uid, limit=10
    )
    print("C unknown mems=", len(unk_mems), "facts=", len(unk_facts))
    if unk_mems or unk_facts:
        failures.append(
            f"(c) unknown must be empty, got mems={unk_mems!r} facts={unk_facts!r}"
        )
    unk_chat = th.process_user_input(
        "What is my spaceship serial number?", user_id=uid
    )
    print("C chat ->", unk_chat)
    low = (unk_chat or "").lower()
    if any(
        x in low
        for x in ("nebulaquartz", "aurora", "pixel", "rover", "carpenter")
    ):
        failures.append(f"(c) chat invented from unrelated memory: {unk_chat!r}")

    # --- (d) Monday speech stored + retrievable ---
    reply = th.process_user_input(
        "What is the codeword?", user_id=uid
    )
    print("D reply ->", reply)
    if not isinstance(reply, str) or not reply.strip():
        failures.append("(d) empty reply from thalamus")
    else:
        with notus._db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM superhuman_memories
                WHERE user_id = %s
                  AND lower(role) IN ('monday', 'assistant', 'abin')
                  AND content = %s
                """,
                (uid, reply.strip()),
            )
            count = int(cur.fetchone()[0])
        print("D exact monday store count=", count)
        if count < 1:
            failures.append(f"(d) reply not stored as monday memory: {reply!r}")
        asked = notus.retrieve_memories_smart(
            reply.strip()[:60], user_id=uid, limit=10
        )
        monday_hits = [
            m
            for m in asked
            if str(m.get("role", "")).lower() in {"monday", "assistant", "abin"}
        ]
        print("D retrieve monday hits=", len(monday_hits))
        if not monday_hits:
            failures.append(
                f"(d) stored reply not retrievable by content: {asked!r}"
            )
        if "NebulaQuartz" not in reply:
            # Chat should also surface the taught codeword.
            failures.append(f"(d) chat did not answer codeword: {reply!r}")

    # --- (e) fragile skip + contradict/update ---
    learned = notus._ingest_personal_facts_from_text(
        "my day is going well", user_id=uid, source="smoke"
    )
    day_facts = [
        f
        for f in notus.recall_facts("day", user_id=uid, limit=20)
        if str(f.get("predicate", "")).lower() == "day"
    ]
    print("E fragile learned=", learned, "day_facts=", day_facts)
    if learned or day_facts:
        failures.append(
            f"(e) fragile extract too eager: learned={learned!r} day={day_facts!r}"
        )

    th.process_user_input("Remember my dog is named Rover.", user_id=uid)
    updated = notus.recall_facts("What is my dog's name?", user_id=uid, limit=10)
    objs = [str(f.get("object", "")) for f in updated]
    print("E update objects=", objs)
    if "Rover" not in objs:
        failures.append(f"(e) contradict/update missed Rover: {updated!r}")
    if "Pixel" in objs:
        failures.append(f"(e) old Pixel still returned: {updated!r}")

    # codeword contradict
    th.process_user_input(
        "Remember the codeword is IronPetal.", user_id=uid
    )
    cw2 = notus.recall_facts("What is the codeword?", user_id=uid, limit=10)
    cw_objs = [str(f.get("object", "")) for f in cw2]
    print("E codeword objects=", cw_objs)
    if "IronPetal" not in cw_objs:
        failures.append(f"(e) codeword update missed IronPetal: {cw2!r}")
    if "NebulaQuartz" in cw_objs:
        failures.append(f"(e) old codeword still returned: {cw2!r}")

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
