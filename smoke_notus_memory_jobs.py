#!/usr/bin/env python3
"""Hard smoke: memory jobs for continuous Monday (not named test_*).

Jobs (pass/fail only):
  1. User durable facts (dog, codeword, job, live-in) survive under filler
     and answer correctly on the live Thalamus path.
  2. Monday reply stored as role=monday and retrievable via
     "what did you say about X".
  3. Contradiction update works (old fact replaced).
  4. Unknown query: empty retrieve + honest no-invent chat answer.
  5. Fragile chatter not stored as facts.
  6. Poison How-it-felt / combined transcript rejected.
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


def _bury(notus, uid: str, n: int, tag: str) -> None:
    for i in range(n):
        notus.store_memory(
            role="user",
            content=f"Filler {tag} {i} about weather lunch traffic podcasts.",
            user_id=uid,
            importance=1.0,
        )


def main() -> int:
    systems = create_core_systems()
    th = systems["thalamus"]
    notus = systems["notus"]
    uid = f"smoke_jobs_{uuid.uuid4().hex[:10]}"
    results: list[tuple[str, str, str]] = []  # (case, PASS|FAIL, detail)

    def mark(case: str, ok: bool, detail: str = "") -> None:
        results.append((case, "PASS" if ok else "FAIL", detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {case}" + (f" — {detail}" if detail else ""))

    # ------------------------------------------------------------------
    # 1. Durable facts under filler + live answers
    # ------------------------------------------------------------------
    th.process_user_input("Remember my dog is named Pixel.", user_id=uid)
    th.process_user_input("Remember the codeword is NebulaQuartz.", user_id=uid)
    th.process_user_input("I work as a carpenter.", user_id=uid)
    th.process_user_input("I live in Boulder.", user_id=uid)
    _bury(notus, uid, 80, "early")

    dog_mems = notus.retrieve_memories_smart(
        "What is my dog's name?", user_id=uid, limit=10
    )
    dog_facts = notus.recall_facts("What is my dog's name?", user_id=uid, limit=10)
    dog_blob = _blob(dog_mems, dog_facts)
    dog_chat = th.process_user_input("What is my dog's name?", user_id=uid)
    mark(
        "1a durable dog under filler + answer",
        "Pixel" in dog_blob and "Pixel" in (dog_chat or ""),
        f"blob={dog_blob[:200]!r} chat={dog_chat!r}",
    )

    cw_mems = notus.retrieve_memories_smart(
        "What is the codeword?", user_id=uid, limit=10
    )
    cw_facts = notus.recall_facts("What is the codeword?", user_id=uid, limit=10)
    cw_blob = _blob(cw_mems, cw_facts)
    cw_chat = th.process_user_input("What is the codeword?", user_id=uid)
    mark(
        "1b durable codeword under filler + answer",
        "NebulaQuartz" in cw_blob and "NebulaQuartz" in (cw_chat or ""),
        f"blob={cw_blob[:200]!r} chat={cw_chat!r}",
    )

    job_facts = notus.recall_facts("What is my job?", user_id=uid, limit=10)
    job_blob = _blob([], job_facts)
    job_chat = th.process_user_input("What is my job?", user_id=uid)
    mark(
        "1c durable job under filler + answer",
        "carpenter" in job_blob.lower() and "carpenter" in (job_chat or "").lower(),
        f"blob={job_blob[:200]!r} chat={job_chat!r}",
    )

    live_facts = notus.recall_facts("Where do I live?", user_id=uid, limit=10)
    live_blob = _blob([], live_facts)
    live_chat = th.process_user_input("Where do I live?", user_id=uid)
    live_ok = (
        "Boulder" in live_blob
        and "Boulder" in (live_chat or "")
        and "live" in (live_chat or "").lower()
        and "lives in is" not in (live_chat or "").lower()
    )
    mark(
        "1d durable live-in under filler + answer",
        live_ok,
        f"blob={live_blob[:200]!r} chat={live_chat!r}",
    )

    # ------------------------------------------------------------------
    # 2. Monday speech stored + retrievable ("what did you say about X")
    # ------------------------------------------------------------------
    # Use a distinctive reply already produced (codeword answer), or force one.
    spoken = (cw_chat or "").strip()
    if not spoken:
        spoken = th.process_user_input("What is the codeword?", user_id=uid) or ""
        spoken = spoken.strip()

    monday_count = 0
    if spoken:
        with notus._db_connection.cursor() as cur:
            cur.execute(
                """
                SELECT COUNT(*) FROM superhuman_memories
                WHERE user_id = %s
                  AND lower(role) = 'monday'
                  AND content = %s
                """,
                (uid, spoken),
            )
            monday_count = int(cur.fetchone()[0])

    ask_said = th.process_user_input(
        "What did you say about NebulaQuartz?", user_id=uid
    )
    said_ok = (
        monday_count >= 1
        and isinstance(ask_said, str)
        and ask_said.strip()
        and "NebulaQuartz" in ask_said
        and "How it felt" not in ask_said
    )
    # Also verify retrieve surfaces monday role for that content.
    said_mems = notus.retrieve_memories_smart(
        "What did you say about NebulaQuartz?", user_id=uid, limit=15
    )
    monday_hits = [
        m
        for m in said_mems
        if str(m.get("role", "")).lower() in {"monday", "assistant", "abin"}
        and "NebulaQuartz" in str(m.get("content", ""))
    ]
    mark(
        "2 Monday reply stored as monday + what-did-you-say",
        said_ok and len(monday_hits) >= 1,
        f"count={monday_count} hits={len(monday_hits)} ask={ask_said!r} spoken={spoken!r}",
    )

    # ------------------------------------------------------------------
    # 3. Contradiction update
    # ------------------------------------------------------------------
    th.process_user_input("Remember my dog is named Rover.", user_id=uid)
    updated = notus.recall_facts("What is my dog's name?", user_id=uid, limit=10)
    objs = [str(f.get("object", "")) for f in updated]
    upd_chat = th.process_user_input("What is my dog's name?", user_id=uid)
    mark(
        "3 contradiction update",
        "Rover" in objs
        and "Pixel" not in objs
        and "Rover" in (upd_chat or "")
        and "Pixel" not in (upd_chat or ""),
        f"objs={objs!r} chat={upd_chat!r}",
    )

    # ------------------------------------------------------------------
    # 4. Unknown: empty retrieve + honest no-invent
    # ------------------------------------------------------------------
    unk_q = "What is my spaceship serial number?"
    unk_mems = notus.retrieve_memories_smart(unk_q, user_id=uid, limit=10)
    unk_facts = notus.recall_facts(unk_q, user_id=uid, limit=10)
    unk_chat = th.process_user_input(unk_q, user_id=uid)
    low = (unk_chat or "").lower()
    invent_leak = any(
        x in low
        for x in (
            "nebulaquartz",
            "pixel",
            "rover",
            "carpenter",
            "boulder",
            "serial",
            "spaceship",
        )
    )
    # Honest: empty retrieve + must not invent unrelated known facts as the answer.
    # "serial"/"spaceship" in answer would mean inventing; known facts leaking is worse.
    invent_known = any(
        x in low for x in ("nebulaquartz", "pixel", "rover", "carpenter", "boulder")
    )
    honest = (
        not unk_mems
        and not unk_facts
        and not invent_known
        and isinstance(unk_chat, str)
        and unk_chat.strip()
    )
    mark(
        "4 unknown empty retrieve + no invent",
        honest,
        f"mems={len(unk_mems)} facts={len(unk_facts)} chat={unk_chat!r}",
    )

    # ------------------------------------------------------------------
    # 5. Fragile chatter not stored as facts
    # ------------------------------------------------------------------
    learned = notus._ingest_personal_facts_from_text(
        "my day is going well", user_id=uid, source="smoke"
    )
    day_facts = [
        f
        for f in notus.recall_facts("day", user_id=uid, limit=20)
        if str(f.get("predicate", "")).lower() == "day"
    ]
    # Also try via live path
    th.process_user_input("my mood is great today", user_id=uid)
    mood_facts = [
        f
        for f in notus.recall_facts("mood", user_id=uid, limit=20)
        if str(f.get("predicate", "")).lower() in {"mood", "day", "feeling", "feelings"}
    ]
    mark(
        "5 fragile chatter not stored as facts",
        not learned and not day_facts and not mood_facts,
        f"learned={learned!r} day={day_facts!r} mood={mood_facts!r}",
    )

    # ------------------------------------------------------------------
    # 6. Poison How-it-felt / combined transcript rejected
    # ------------------------------------------------------------------
    poison_felt = notus.process_message(
        {
            "type": "store",
            "content": {
                "role": "user",
                "content": (
                    "How it felt: warm and curious.\n"
                    "What it meant: connection mattered."
                ),
                "user_id": uid,
            },
        }
    )
    poison_combo = notus.process_message(
        {
            "type": "store",
            "content": {
                "role": "user",
                "content": "user: hello there\nabin: hi back",
                "user_id": uid,
            },
        }
    )
    felt_stored = bool((poison_felt.get("content") or {}).get("stored"))
    combo_stored = bool((poison_combo.get("content") or {}).get("stored"))
    # Also ensure retrieve does not surface a manually-forced poison if somehow present
    # (store path must reject — that is the job).
    mark(
        "6 poison How-it-felt + combined transcript rejected",
        not felt_stored and not combo_stored,
        f"felt={poison_felt!r} combo={poison_combo!r}",
    )

    shutdown_core_systems(systems)

    print("---")
    fails = [r for r in results if r[1] == "FAIL"]
    for case, status, detail in results:
        print(f"{status}: {case}")
    if fails:
        print(f"OVERALL FAIL ({len(fails)} cases)")
        return 1
    print("OVERALL PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
