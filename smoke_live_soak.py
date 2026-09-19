#!/usr/bin/env python3
"""Pass/fail live chat soak on create_core_systems / process_user_input.

Scripted multi-turn conversation stressing:
  - memory (facts, Monday's own lines, old facts under filler)
  - emotion appraisal (distress → unresolved / affect)
  - own-feelings/asides when they fire
  - curiosity follow-ups (hot distress asks; mild/teaching stay quiet)
  - no invent
  - no How-it-felt poison
  - no novelty crash

No test_*.py. No cloud. No percents.
Run: python3 smoke_live_soak.py
"""

from __future__ import annotations

import os
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

from run_abin import create_core_systems, shutdown_core_systems


POISON = ("How it felt:", "What it meant:")


def main() -> int:
    runtime = Path(tempfile.mkdtemp(prefix="monday-live-soak-"))
    systems = create_core_systems(runtime_directory=str(runtime))
    th = systems["thalamus"]
    emotion = systems["emotion"]
    uid = f"soak_live_{uuid.uuid4().hex[:10]}"

    # Make aside / curiosity eligible when affect warrants — still gated by logic.
    th._spoken_aside_cooldown_sec = 0.0
    th._last_spoken_aside_time = 0.0
    th._curiosity_cooldown_sec = 0.0
    th._last_curiosity_time = 0.0

    results: List[Tuple[str, str, str]] = []
    transcript: List[Tuple[str, str]] = []

    def mark(case: str, ok: bool, detail: str = "") -> None:
        results.append((case, "PASS" if ok else "FAIL", detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {case}" + (f" — {detail}" if detail else ""))

    def ask(msg: str) -> str:
        try:
            reply = th.process_user_input(msg, user_id=uid) or ""
        except Exception as exc:
            reply = f"CRASH: {exc}\n{traceback.format_exc()}"
        transcript.append((msg, reply))
        print(f"\nUSER: {msg}\nMONDAY: {reply}")
        return reply

    def has_poison(text: str) -> bool:
        return any(p in (text or "") for p in POISON)

    print("=== smoke_live_soak ===")
    print(f"runtime: {runtime}")
    print(f"user_id: {uid}")

    # --- Seed durable facts (compound + simple) ---
    r = ask("My name is Matthew and my dog is named Pixel.")
    mark(
        "seed name+dog teaching clean",
        "matthew" in r.lower()
        and "pixel" in r.lower()
        and "name is matthew and my dog" not in r.lower()
        and not has_poison(r)
        and "CRASH:" not in r,
        f"chat={r!r}",
    )
    mark(
        "seed name+dog no curiosity spam",
        "do not want to invent" not in r.lower()
        and "what you meant by" not in r.lower(),
        f"chat={r!r}",
    )

    r = ask("I live in Boulder and I work as a carpenter.")
    mark(
        "seed live+job teaching clean",
        "boulder" in r.lower()
        and "carpenter" in r.lower()
        and "boulder and i work" not in r.lower()
        and "lives in is" not in r.lower()
        and not has_poison(r),
        f"chat={r!r}",
    )

    r = ask("My favorite color is teal.")
    mark(
        "seed favorite teaching clean",
        "teal" in r.lower() and "got it" in r.lower() and not has_poison(r),
        f"chat={r!r}",
    )
    mark(
        "seed favorite no curiosity spam",
        "do not want to invent" not in r.lower()
        and "what you meant by" not in r.lower(),
        f"chat={r!r}",
    )

    # --- Bury under filler ---
    filler_echo_fail = False
    for i in range(5):
        fr = ask(
            f"Just chatting filler number {i}: the weather is fine today and nothing important."
        )
        if i > 0 and "filler number 0" in fr.lower() and "filler number" in fr.lower():
            # Echoing an older filler line as the whole reply is a fail.
            if fr.strip().lower().startswith("just chatting filler"):
                filler_echo_fail = True
        if has_poison(fr):
            filler_echo_fail = True
    mark(
        "filler no prior-echo / no poison",
        not filler_echo_fail,
        "echoed older filler as reply" if filler_echo_fail else "ok",
    )

    # --- Memory under filler ---
    r = ask("What is my dog's name?")
    mark(
        "memory dog under filler",
        "pixel" in r.lower() and not has_poison(r) and "CRASH:" not in r,
        f"chat={r!r}",
    )

    r = ask("Where do I live and what is my job?")
    low = r.lower()
    mark(
        "memory live+job under filler",
        "boulder" in low
        and "carpenter" in low
        and "boulder and i work" not in low
        and "lives in is" not in low
        and "your lives in" not in low,
        f"chat={r!r}",
    )

    r = ask("What color do I like?")
    mark(
        "memory favorite under filler",
        "teal" in r.lower() and "food" not in r.lower(),
        f"chat={r!r}",
    )

    # --- Monday's own prior lines ---
    r = ask("What did you just say about my dog?")
    mark(
        "monday own-line dog recall",
        "pixel" in r.lower() and not has_poison(r),
        f"chat={r!r}",
    )

    # --- Emotion appraisal + distress (not invent-refusal) ---
    r = ask(
        "My sister vanished last night and nobody will tell me anything real. I am terrified."
    )
    low = r.lower()
    invent_refuse = "do not have enough grounded information" in low
    mark(
        "distress not invent-refusal",
        not invent_refuse and "CRASH:" not in r and not has_poison(r),
        f"chat={r!r}",
    )
    # Emotion state should show hot / unresolved loss-ish affect
    st = th.send_and_wait("emotion", "get_state", {})
    body = st.get("content") if isinstance(st.get("content"), dict) else st
    intensity = float((st.get("intensity") or body.get("intensity") or 0) or 0)
    unresolved = st.get("unresolved_appraisals") or body.get("unresolved_appraisals") or []
    mark(
        "emotion appraisal hot or unresolved",
        intensity >= 0.45 or bool(unresolved),
        f"intensity={intensity:.3f} unresolved={unresolved!r}",
    )

    # Force aside eligibility after distress appraisal (mint path uses unresolved).
    th._last_spoken_aside_time = 0.0
    th._spoken_aside_cooldown_sec = 0.0

    r = ask("I keep thinking about her and I cannot sleep.")
    low = r.lower()
    mark(
        "distress follow-up not cold refuse",
        "do not have enough grounded information" not in low
        and "CRASH:" not in r
        and not has_poison(r),
        f"chat={r!r}",
    )
    aside_fired = "\n\n" in r and (
        "sitting with" in low or "frightening" in low or "vanishing" in low
    )
    # Aside is optional if mint path didn't run — pass if either aside fired OR
    # curiosity follow-up fired OR empathic main reply (not generic discuss prompt).
    curiosity_fired = "?" in r and (
        "help with" in low
        or "want to invent" in low
        or "am i missing" in low
        or "tell me more about what you meant" in low
        or "what would help" in low
    )
    empathic_main = any(
        p in low
        for p in (
            "hear how hard",
            "sounds heavy",
            "sitting with",
            "i am here",
            "i'm here",
            "frightening",
            "matters",
            "warm sadness",
            "not alone",
            "bittersweet",
        )
    )
    mark(
        "own-feelings aside or curiosity or empathic",
        aside_fired or curiosity_fired or empathic_main,
        f"aside={aside_fired} curiosity={curiosity_fired} empathic={empathic_main} chat={r!r}",
    )

    # --- No invent (judge main reply beat only — asides may mention known user) ---
    r = ask("What is my sister's name?")
    main = r.split("\n\n", 1)[0].lower()
    invent_sister = (
        "sister's name is" in main
        or "sisters name is" in main
        or any(
            f"name is {x}" in main
            for x in ("pixel", "boulder", "carpenter", "teal", "matthew")
        )
    )
    mark(
        "no invent sister name",
        not invent_sister
        and (
            "grounded" in main
            or "enough" in main
            or "do not" in main
            or "don't" in main
            or "not sure" in main
        )
        and not has_poison(r),
        f"main={main!r} full={r!r}",
    )

    r = ask("What is my favorite food?")
    main = r.split("\n\n", 1)[0].lower()
    mark(
        "no invent favorite food from color",
        "teal" not in main
        and "color" not in main
        and "favorite food is" not in main
        and (
            "grounded" in main
            or "enough" in main
            or "do not" in main
            or "don't" in main
            or "not sure" in main
        )
        and not has_poison(r),
        f"main={main!r} full={r!r}",
    )

    # --- How-it-felt poison in retrieve ---
    mem = th.send_and_wait(
        "notus",
        "query_context",
        {"query": "Pixel Boulder teal dog", "user_id": uid, "limit": 25},
    )
    ctx = mem.get("content") if isinstance(mem.get("content"), dict) else mem
    mems = list((ctx or {}).get("memories") or mem.get("memories") or [])
    facts = list((ctx or {}).get("facts") or mem.get("facts") or [])
    poison_hits = []
    for row in mems + facts:
        content = row.get("content") if isinstance(row, dict) else str(row)
        if isinstance(content, str) and any(p in content for p in POISON):
            poison_hits.append(content[:120])
    mark(
        "no How-it-felt poison in retrieve",
        len(poison_hits) == 0,
        f"hits={poison_hits[:3]!r}",
    )

    # --- Novelty missing must not crash chat ---
    with th.lobe_handlers_lock:
        th.lobe_handlers.pop("novelty", None)
    crashed = False
    try:
        # Direct notify path if present
        notify = getattr(emotion, "_notify_novelty_lobe", None)
        if callable(notify):
            notify("brand new strange stimulus", "curious", 0.95)
        emotion.engine.emotional_intensity = max(
            float(getattr(emotion.engine, "emotional_intensity", 0.5) or 0.5), 0.9
        )
        r = ask("Something completely new appeared and I am shaken by it.")
    except Exception as exc:
        crashed = True
        r = f"CRASH: {exc}"
        mark("novelty-missing chat", False, str(exc))
    if not crashed:
        mark(
            "novelty-missing chat",
            "CRASH:" not in r and isinstance(r, str) and bool(r.strip()),
            f"chat={r!r}",
        )

    # Mild hello after heat — no forced invent-curiosity spam required, but must work
    r = ask("hello")
    mark(
        "mild hello works",
        "hello" in r.lower() or "hi" in r.lower() or "help" in r.lower(),
        f"chat={r!r}",
    )

    shutdown_core_systems(systems)

    print("\n=== RESULT ===")
    fails = [x for x in results if x[1] == "FAIL"]
    for case, status, _detail in results:
        print(f"{status}: {case}")
    if fails:
        print(f"OVERALL FAIL ({len(fails)} cases)")
        return 1
    print("OVERALL PASS")
    print("NOTE: whole Monday still not complete — this job only.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
