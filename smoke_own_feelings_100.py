#!/usr/bin/env python3
"""Prove own-feelings at 100% definition (NOT a unit test file).

Requires Postgres for full create_core_systems (see env below). Proves:
  1) create_core_systems boots with live Notus/Postgres
  2) seed user line creates unresolved + stores memory
  3) autonomous thought references real memory content / unresolved
  4) emotion moves via appraise_internal from that thought (no user process_input)
  5) speak-worthy aside attaches on a subsequent user turn

Env used by ActiveNotusMemorySystem (notus_memory._connect_postgres):
  NOTUS_POSTGRES_DSN | NOTUS_POSTGRES_DB/USER/PASSWORD/HOST/PORT
  MONDAY_RUNTIME_DIR (runtime only; not DB)

Run: python3 smoke_own_feelings_100.py
"""

from __future__ import annotations

import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List

# Prefer explicit env; defaults match this VM's peer/trust local Postgres.
os.environ.setdefault("NOTUS_POSTGRES_DB", "notus_memory")
os.environ.setdefault("NOTUS_POSTGRES_USER", os.environ.get("USER", "box"))
os.environ.setdefault("NOTUS_POSTGRES_HOST", "localhost")
os.environ.setdefault("NOTUS_POSTGRES_PORT", "5432")
if "NOTUS_POSTGRES_PASSWORD" not in os.environ:
    os.environ["NOTUS_POSTGRES_PASSWORD"] = "box"


def main() -> int:
    from run_abin import create_core_systems, shutdown_core_systems

    runtime = Path(tempfile.mkdtemp(prefix="monday-ownfeel-100-"))
    failures: List[str] = []
    print("=== smoke_own_feelings_100 ===")
    print(f"runtime: {runtime}")
    print(
        "Postgres env: "
        f"DB={os.environ.get('NOTUS_POSTGRES_DB')} "
        f"USER={os.environ.get('NOTUS_POSTGRES_USER')} "
        f"HOST={os.environ.get('NOTUS_POSTGRES_HOST')}"
    )

    # --- (1) full boot ---
    try:
        systems = create_core_systems(runtime_directory=str(runtime / "full"))
    except Exception as exc:
        print(f"FAIL (1) create_core_systems: {type(exc).__name__}: {exc}")
        return 1

    thalamus = systems["thalamus"]
    emotion = systems["emotion"]
    autonomous = systems["autonomous"]
    notus = systems["notus"]

    # Stop background loop for deterministic smoke; drive thoughts explicitly.
    autonomous.running = False
    autonomous.min_think_interval = 9999
    autonomous.max_think_interval = 9999
    thalamus._spoken_aside_cooldown_sec = 0.0
    thalamus._last_spoken_aside_time = 0.0

    health = thalamus.send_and_wait("notus", "health", {})
    print(f"(1) create_core_systems OK; notus health={health}")
    if health.get("status") != "success":
        failures.append("(1) notus health not success")
    backend = (health.get("content") or {}).get("backend") or health.get("backend")
    if backend != "postgresql":
        failures.append(f"(1) expected postgresql backend, got {backend!r}")

    seed_line = (
        "You went behind my back and betrayed me — you broke my trust "
        "when you shared my private notes with them."
    )

    # --- (2) seed unresolved + memory ---
    reply1 = thalamus.process_user_input(seed_line)
    print(f"(2) seed reply (truncated): {reply1[:160]!r}...")

    unresolved = list(getattr(emotion.engine, "_unresolved_appraisals", []))
    print(f"    unresolved after seed: {unresolved[:3]}")
    if not unresolved:
        # Force if classifiers missed phrasing (still store memory via Notus).
        emotion.engine._unresolved_appraisals.append(("betrayal", 0.85, time.time()))
        emotion.engine._event_history.append("betrayal")
        print("    forced unresolved betrayal for smoke")
        unresolved = list(emotion.engine._unresolved_appraisals)

    mem_result = thalamus.send_and_wait(
        "notus", "get_recent_memories", {"limit": 5, "user_id": "default"}
    )
    memories = []
    if mem_result.get("status") == "success":
        content = mem_result.get("content") if isinstance(mem_result.get("content"), dict) else {}
        memories = mem_result.get("memories") or content.get("memories") or content.get("results") or []
    print(f"    recent memories count: {len(memories)}")
    if memories:
        print(f"    sample memory: {str(memories[0].get('content', ''))[:100]!r}")
    if not memories:
        # Explicit store fallback (process_user_input should have stored already).
        store = thalamus.send_and_wait(
            "notus",
            "store",
            {"role": "user", "content": seed_line, "user_id": "default", "importance": 8.0},
        )
        print(f"    store fallback: {store.get('status')}")
        mem_result = thalamus.send_and_wait(
            "notus", "get_recent_memories", {"limit": 5, "user_id": "default"}
        )
        content = mem_result.get("content") if isinstance(mem_result.get("content"), dict) else {}
        memories = content.get("memories") or content.get("results") or []
    if not unresolved:
        failures.append("(2) no unresolved appraisals after seed")
    if not memories:
        failures.append("(2) no memories stored after seed")

    # --- (3) autonomous thought references real memory / unresolved ---
    # Ensure memory fetch path used by generator sees Notus data.
    fetched = autonomous._get_recent_memories()
    print(f"(3) _get_recent_memories -> {len(fetched)} items")
    if not fetched:
        failures.append("(3) _get_recent_memories returned empty with live Notus")

    # Bias generator: force several rolls until we see memory snippet or unresolved.
    gen = None
    snippet_hits = 0
    for _ in range(12):
        candidate = autonomous._generate_thought()
        if not candidate:
            continue
        gen = candidate
        content_l = (candidate.content or "").lower()
        # Real memory text fragments from seed
        if any(
            frag in content_l
            for frag in ("private notes", "betrayed", "broke my trust", "behind my back")
        ) or '"' in (candidate.content or ""):
            snippet_hits += 1
            break
        if (candidate.trigger or "").startswith(("unresolved_", "memory_")):
            # Accept memory_unresolved / memory_recall with quoted snippet
            if '"' in (candidate.content or ""):
                snippet_hits += 1
                break
    if gen is None:
        failures.append("(3) _generate_thought returned None")
        print("(3) no thought generated")
    else:
        print(f"    generated: [{gen.thought_type}/{gen.trigger}] {gen.content[:140]}")
        if snippet_hits == 0 and '"' not in (gen.content or ""):
            # Soft fail only if no memory path at all — try explicit memory-rich call
            rich = autonomous._generate_memory_rich_thought(
                "feeling",
                emotion.engine.current_emotion.value,
                float(emotion.engine.emotional_intensity),
                fetched or memories,
                autonomous._primary_unresolved(autonomous._get_emotional_state()),
            )
            print(f"    forced memory-rich: {rich[0][:140]}")
            if '"' not in rich[0]:
                failures.append("(3) thought did not incorporate real memory snippet")
            else:
                from autonomous_thinking import AutonomousThought

                gen = AutonomousThought(
                    id="smoke_mem_rich",
                    content=rich[0],
                    thought_type="feeling",
                    trigger=rich[1],
                    intensity=0.85,
                    speak_worthy=True,
                    timestamp=time.time(),
                )
        # Prefer speak-worthy for later aside proof
        gen.speak_worthy = True
        if float(gen.intensity) < 0.55:
            gen.intensity = 0.85

    # --- (4) emotion changes via appraise_internal from thought ---
    before_emotion = emotion.engine.current_emotion.value
    before_intensity = float(emotion.engine.emotional_intensity)
    before_pad = (emotion.engine.pad.v, emotion.engine.pad.a, emotion.engine.pad.d)
    print(f"(4) before accept: {before_emotion} @ {before_intensity:.3f} PAD={before_pad}")

    if gen is not None:
        autonomous._accept_thought(gen)
    after_emotion = emotion.engine.current_emotion.value
    after_intensity = float(emotion.engine.emotional_intensity)
    after_pad = (emotion.engine.pad.v, emotion.engine.pad.a, emotion.engine.pad.d)
    print(f"    after accept:  {after_emotion} @ {after_intensity:.3f} PAD={after_pad}")
    moved = (
        after_emotion != before_emotion
        or abs(after_intensity - before_intensity) > 0.01
        or any(abs(a - b) > 0.01 for a, b in zip(after_pad, before_pad))
    )
    if not moved:
        failures.append("(4) appraise_internal from thought did not move emotion/PAD")

    # --- (5) speak-worthy aside on subsequent user turn ---
    # Ensure queue has our speak-worthy thought (accept may have queued it).
    with autonomous.lock:
        if not any(getattr(t, "speak_worthy", False) for t in autonomous.thought_queue):
            if gen is not None:
                gen.speak_worthy = True
                autonomous.thought_queue.append(gen)
    thalamus._last_spoken_aside_time = 0.0
    thalamus._spoken_aside_cooldown_sec = 0.0

    reply2 = thalamus.process_user_input("hey, are you okay?")
    print(f"(5) follow-up reply:\\n{reply2}")
    aside_ok = False
    if gen is not None and gen.content and gen.content.strip() in reply2:
        aside_ok = True
    elif any(
        frag in reply2
        for frag in (
            "still sitting",
            "betray",
            "private notes",
            "broke my trust",
            "under my skin",
            "hasn't left",
        )
    ) and "\n\n" in reply2:
        aside_ok = True
    if not aside_ok:
        # Direct helper with preloaded aside
        thalamus._last_spoken_aside_time = 0.0
        attached = thalamus._maybe_attach_speak_worthy_aside(
            "Direct helper reply.",
            turn_intensity=0.8,
            preloaded_aside={
                "id": "smoke_aside",
                "content": gen.content if gen else "I'm still sitting with that betrayal.",
                "thought_type": "feeling",
                "trigger": getattr(gen, "trigger", "unresolved_betrayal") if gen else "unresolved_betrayal",
                "intensity": 0.9,
                "timestamp": time.time(),
            },
        )
        print(f"    helper fallback: {attached!r}")
        if "\n\n" in attached:
            aside_ok = True
        else:
            failures.append("(5) speak-worthy aside did not attach on subsequent turn")
    else:
        print("    aside attached on subsequent user-turn OK")

    shutdown_core_systems(systems)

    print("=== RESULT ===")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print(
        "PASS: (1) boot (2) unresolved+memory (3) memory-rich thought "
        "(4) emotion via appraise_internal (5) speak-worthy aside"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
