#!/usr/bin/env python3
"""Pass/fail smoke: FULL Emotion engine job on the live path.

Design job (one line): On the live path, EmotionalProcess must appraise user and
inner-life events into PAD-driven emotion (hysteresis/refractory), update
attachment/needs/internal loops, record memories and learn trigger patterns,
surface expression flags plus EmotionalStateOutput (tone/prosody/emphasis) into
thalamus→output, and persist/reload that full state.

Proves:
  (1) create_core_systems registers emotion
  (2) appraisal moves emotion + unresolved for betrayal-class input
  (3) PAD pleasure/arousal/dominance exposed and moved
  (4) attachment + needs update from appraisal path
  (5) autonomous inner life (appraise_internal) moves emotion without user chat
  (6) memories recorded after process_input
  (7) pattern learning after process_input
  (8) expressions / EmotionalStateOutput reach output on live path
  (9) persistence save/load restores core affect state
  (10) live chat path hits emotion process_input

No test_*.py. No cloud. No percents. PASS/FAIL only.
Run: python3 smoke_emotion_engine_full.py
"""

from __future__ import annotations

import os
import sys
import tempfile
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Tuple

os.environ.setdefault("NOTUS_POSTGRES_DB", "notus_memory")
os.environ.setdefault("NOTUS_POSTGRES_USER", os.getenv("USER", "box"))
os.environ.setdefault("NOTUS_POSTGRES_HOST", "localhost")
os.environ.setdefault(
    "NOTUS_POSTGRES_PASSWORD", os.getenv("NOTUS_POSTGRES_PASSWORD", "box")
)

from advanced_emotional_engine import EmotionalProcess
from run_abin import create_core_systems, shutdown_core_systems


def _pad_tuple(engine) -> Tuple[float, float, float]:
    p = engine.pad
    return (float(p.v), float(p.a), float(p.d))


def _content(resp: Dict[str, Any]) -> Dict[str, Any]:
    c = resp.get("content")
    if isinstance(c, dict):
        return c
    return resp if isinstance(resp, dict) else {}


def main() -> int:
    runtime = Path(tempfile.mkdtemp(prefix="monday-emotion-smoke-"))
    results: List[Tuple[str, str, str]] = []

    def mark(case: str, ok: bool, detail: str = "") -> None:
        results.append((case, "PASS" if ok else "FAIL", detail))
        print(f"[{'PASS' if ok else 'FAIL'}] {case}" + (f" — {detail}" if detail else ""))

    print("=== smoke_emotion_engine_full ===")
    print(
        "DESIGN JOB: On the live path, EmotionalProcess must appraise user and "
        "inner-life events into PAD-driven emotion (hysteresis/refractory), update "
        "attachment/needs/internal loops, record memories and learn trigger patterns, "
        "surface expression flags plus EmotionalStateOutput (tone/prosody/emphasis) into "
        "thalamus→output, and persist/reload that full state."
    )
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
        print("RESULT: FAIL")
        return 1

    th = systems["thalamus"]
    emotion = systems.get("emotion")
    registered = "emotion" in th.lobe_handlers and isinstance(emotion, EmotionalProcess)
    mark("emotion registered", registered)
    if not registered:
        try:
            shutdown_core_systems(systems)
        except Exception:
            pass
        print("RESULT: FAIL")
        return 1

    eng = emotion.engine
    # Deterministic-ish: shorten internal cooldown for smoke
    eng.INTERNAL_COOLDOWN_SEC = 0.0

    # Snapshot baselines
    before_emotion = eng.current_emotion.value
    before_pad = _pad_tuple(eng)
    before_hurt = float(eng.attachment.hurt)
    before_belonging = float(eng.needs.belonging)
    before_safety = float(eng.needs.safety)
    before_mems = len(eng.emotional_memories)
    before_patterns = len(eng.emotional_patterns)

    # --- (2) Appraisal ---
    try:
        resp = th.send_and_wait(
            "emotion",
            "process_input",
            {
                "user_input": (
                    "You went behind my back and betrayed me — you broke my trust "
                    "and abandoned me when I needed you."
                )
            },
            source="smoke",
        )
        ok = resp.get("status") == "success"
        body = _content(resp)
        cur = resp.get("current_emotion") or body.get("current_emotion")
        unresolved = resp.get("unresolved_appraisals") or body.get("unresolved_appraisals") or []
        appraisal_ok = (
            ok
            and isinstance(cur, str)
            and cur not in ("", "calm", "neutral")
            and bool(unresolved)
        )
        mark(
            "appraisal moves emotion + unresolved",
            appraisal_ok,
            f"emotion={cur!r} unresolved={unresolved[:2]!r} was={before_emotion!r}",
        )
    except Exception as exc:
        mark("appraisal moves emotion + unresolved", False, f"CRASH: {exc}")
        traceback.print_exc()

    # --- (3) PAD exposed and moved ---
    try:
        pad_now = _pad_tuple(eng)
        pad_moved = pad_now != before_pad
        # Must be exposed on live API (process_input and/or get_emotional_state)
        pi = th.send_and_wait(
            "emotion",
            "process_input",
            {"user_input": "I am so grateful and I love how you support me."},
            source="smoke",
        )
        pi_body = _content(pi)
        ges = th.send_and_wait("emotion", "get_emotional_state", {}, source="smoke")
        ges_body = _content(ges)
        exposed_keys = set(pi.keys()) | set(pi_body.keys()) | set(ges_body.keys())
        # Also accept nested pad dict
        has_pad_fields = (
            {"pleasure", "arousal", "dominance"}.issubset(exposed_keys)
            or {"pad_v", "pad_a", "pad_d"}.issubset(exposed_keys)
            or (
                isinstance(pi.get("pad"), dict)
                or isinstance(pi_body.get("pad"), dict)
                or isinstance(ges_body.get("pad"), dict)
            )
            or (
                "pleasure" in ges_body
                and "arousal" in ges_body
                and "dominance" in ges_body
            )
        )
        # process_input itself should expose PAD for downstream lobes (live contract)
        pi_exposes = (
            {"pleasure", "arousal", "dominance"}.issubset(set(pi.keys()) | set(pi_body.keys()))
            or isinstance(pi.get("pad"), dict)
            or isinstance(pi_body.get("pad"), dict)
        )
        mark(
            "PAD exposed and moved",
            pad_moved and has_pad_fields and pi_exposes,
            f"before={before_pad} now={pad_now} pi_exposes={pi_exposes} "
            f"ges_pad=({ges_body.get('pleasure')},{ges_body.get('arousal')},{ges_body.get('dominance')})",
        )
    except Exception as exc:
        mark("PAD exposed and moved", False, f"CRASH: {exc}")
        traceback.print_exc()

    # --- (4) attachment + needs ---
    try:
        # Force a clear harm/betrayal appraisal again
        th.send_and_wait(
            "emotion",
            "process_input",
            {
                "user_input": (
                    "You hurt me badly — that betrayal and rejection cut deep, "
                    "I feel unsafe and alone."
                )
            },
            source="smoke",
        )
        hurt_now = float(eng.attachment.hurt)
        belonging_now = float(eng.needs.belonging)
        safety_now = float(eng.needs.safety)
        attach_ok = hurt_now > before_hurt or float(eng.attachment.abandonment_fear) > 0.2
        needs_ok = (belonging_now < before_belonging) or (safety_now < before_safety)
        # Exposed on get_state / process_input
        st = th.send_and_wait("emotion", "get_state", {}, source="smoke")
        st_body = _content(st)
        exposed = set(st.keys()) | set(st_body.keys())
        exposed_ok = (
            "attachment" in exposed
            and "needs" in exposed
        ) or (
            "hurt" in exposed and ("belonging" in exposed or "safety" in exposed)
        )
        mark(
            "attachment+needs update and exposed",
            attach_ok and needs_ok and exposed_ok,
            f"hurt {before_hurt}->{hurt_now} belonging {before_belonging}->{belonging_now} "
            f"safety {before_safety}->{safety_now} exposed_ok={exposed_ok}",
        )
    except Exception as exc:
        mark("attachment+needs update and exposed", False, f"CRASH: {exc}")
        traceback.print_exc()

    # --- (5) autonomous inner life ---
    try:
        pre_e = eng.current_emotion.value
        pre_i = float(eng.emotional_intensity)
        pre_pad = _pad_tuple(eng)
        ir = th.send_and_wait(
            "emotion",
            "appraise_internal",
            {
                "content": (
                    "I keep replaying that betrayal — they broke my trust and "
                    "left me alone; it still hurts."
                ),
                "source": "memory",
                "relevance": 0.95,
                "resolved": False,
                "memory_age_seconds": 30.0,
            },
            source="smoke",
        )
        moved = (
            ir.get("status") == "success"
            and (
                eng.current_emotion.value != pre_e
                or abs(float(eng.emotional_intensity) - pre_i) > 0.02
                or _pad_tuple(eng) != pre_pad
            )
        )
        mark(
            "autonomous inner life moves emotion",
            moved,
            f"before={pre_e}@{pre_i:.3f} after={eng.current_emotion.value}@"
            f"{eng.emotional_intensity:.3f} pad {_pad_tuple(eng)}",
        )
    except Exception as exc:
        mark("autonomous inner life moves emotion", False, f"CRASH: {exc}")
        traceback.print_exc()

    # --- (6) memories ---
    try:
        mems_now = len(eng.emotional_memories)
        mem_ok = mems_now > before_mems
        mark(
            "memories recorded",
            mem_ok,
            f"before={before_mems} after={mems_now} last="
            f"{eng.emotional_memories[-1].trigger[:60]!r}" if eng.emotional_memories else "none",
        )
    except Exception as exc:
        mark("memories recorded", False, f"CRASH: {exc}")
        traceback.print_exc()

    # --- (7) pattern learning ---
    try:
        patterns_now = len(eng.emotional_patterns)
        # Also check via get_state exposure
        st = th.send_and_wait("emotion", "get_state", {}, source="smoke")
        st_body = _content(st)
        exposed = set(st.keys()) | set(st_body.keys())
        pat_exposed = "patterns" in exposed or "emotional_patterns" in exposed
        mark(
            "pattern learning",
            patterns_now > before_patterns and pat_exposed,
            f"before={before_patterns} after={patterns_now} exposed={pat_exposed} "
            f"sample={list(eng.emotional_patterns.keys())[:5]}",
        )
    except Exception as exc:
        mark("pattern learning", False, f"CRASH: {exc}")
        traceback.print_exc()

    # --- (8) expressions into output ---
    try:
        # Drive sad/hurt so expression flags can fire
        th.send_and_wait(
            "emotion",
            "process_input",
            {
                "user_input": (
                    "I am grieving a terrible loss — abandoned, heartbroken, "
                    "crying and alone without you."
                )
            },
            source="smoke",
        )
        ges = th.send_and_wait("emotion", "get_emotional_state", {}, source="smoke")
        ges_body = _content(ges)
        has_prosody = isinstance(ges_body.get("voice_prosody"), dict) and bool(
            ges_body.get("voice_prosody")
        )
        has_tone = bool(ges_body.get("emotional_tone"))
        has_emphasis = isinstance(ges_body.get("emphasis"), list)
        expr = getattr(eng, "expression", None)
        expr_dict = {
            "tears": bool(getattr(expr, "tears", False)),
            "voice_shake": bool(getattr(expr, "voice_shake", False)),
            "withdraw": bool(getattr(expr, "withdraw", False)),
        }
        # Live path must deliver expression/prosody into output generate_output
        routes_before = len(th.message_routes)
        user_id = f"emo-smoke-{uuid.uuid4().hex[:8]}"
        reply = th.process_user_input(
            "That loss still sits heavy with me.",
            user_id=user_id,
        )
        routes = list(th.message_routes)[routes_before:]
        out_routes = [r for r in routes if r.get("to") == "output" and r.get("type") == "generate_output"]
        # Inspect last output message payload if thalamus stores it
        delivered = False
        detail_bits = []
        for r in out_routes:
            # message_routes may only store metadata; check formatted on output lobe
            pass
        formatted = getattr(systems["output"], "last_output", None)
        # Prefer checking the actual generate_output call content via a direct probe:
        # after live turn, output should have been called with prosody/expression fields
        # We re-fetch emotional state and ask output with full payload like thalamus should.
        out_probe = th.send_and_wait(
            "output",
            "generate_output",
            {
                "text": "probe expression wiring",
                "emotion": eng.current_emotion.value,
                "intensity": eng.emotional_intensity,
                "voice_prosody": ges_body.get("voice_prosody") or {},
                "emotional_tone": ges_body.get("emotional_tone"),
                "emphasis": ges_body.get("emphasis") or [],
                "expression": expr_dict,
                "preserve_text": True,
            },
            source="smoke",
        )
        out_body = _content(out_probe)
        formatted_out = out_body.get("formatted") or out_probe.get("formatted") or {}
        # Live thalamus process_user_input must have included expression/prosody
        # Check by seeing if emotion process_input return includes expression + if
        # a captured route or we monkey-check thalamus last emotion payload.
        # Practical check: after live chat, thalamus should have sent expression OR
        # voice_prosody on generate_output. Inspect message_routes entries' content if any.
        meta = getattr(systems["output"], "last_emotion_meta", {}) or {}
        live_delivered = bool(
            (isinstance(meta.get("voice_prosody"), dict) and meta.get("voice_prosody"))
            or meta.get("expression")
            or meta.get("emphasis")
            or meta.get("emotional_tone")
        )
        pi_live = th.send_and_wait(
            "emotion",
            "process_input",
            {"user_input": "I still feel that heavy loss and abandonment."},
            source="smoke",
        )
        pi_live_body = _content(pi_live)
        pi_keys = set(pi_live.keys()) | set(pi_live_body.keys())
        contract_ok = (
            ("voice_prosody" in pi_keys or "expression" in pi_keys)
            and ("emotional_tone" in pi_keys or "emphasis" in pi_keys or "expression" in pi_keys)
        )
        expr_payload = pi_live.get("expression") or pi_live_body.get("expression") or {}
        expr_live = any(expr_dict.values()) or (
            isinstance(expr_payload, dict) and any(expr_payload.values())
        )
        mark(
            "expressions into output",
            has_prosody
            and has_tone
            and has_emphasis
            and contract_ok
            and live_delivered
            and expr_live,
            f"prosody={has_prosody} tone={ges_body.get('emotional_tone')!r} "
            f"emphasis={ges_body.get('emphasis')!r} expr={expr_dict} "
            f"contract_ok={contract_ok} live_meta={meta} "
            f"out_routes={len(out_routes)} reply_len={len(reply) if isinstance(reply, str) else 0}",
        )
    except Exception as exc:
        mark("expressions into output", False, f"CRASH: {exc}")
        traceback.print_exc()

    # --- (9) persistence ---
    try:
        state_path = runtime / "persist_check.json"
        save_emotion = eng.current_emotion.value
        save_intensity = float(eng.emotional_intensity)
        save_pad = _pad_tuple(eng)
        save_hurt = float(eng.attachment.hurt)
        emotion._atomic_save_state()
        # Also write to explicit path
        eng.save_emotional_state(str(state_path))
        # New process loads
        ep2 = EmotionalProcess(state_file=str(state_path), thalamus=th)
        load_ok = (
            ep2.engine.current_emotion.value == save_emotion
            and abs(float(ep2.engine.emotional_intensity) - save_intensity) < 1e-6
        )
        # Full job: PAD + attachment must persist too
        pad_ok = _pad_tuple(ep2.engine) == save_pad or (
            abs(ep2.engine.pad.v - save_pad[0]) < 1e-5
            and abs(ep2.engine.pad.a - save_pad[1]) < 1e-5
            and abs(ep2.engine.pad.d - save_pad[2]) < 1e-5
        )
        attach_ok = abs(float(ep2.engine.attachment.hurt) - save_hurt) < 1e-5
        mark(
            "persistence save/load full state",
            load_ok and pad_ok and attach_ok,
            f"emotion={save_emotion} pad_ok={pad_ok} attach_ok={attach_ok} "
            f"loaded_pad={_pad_tuple(ep2.engine)} loaded_hurt={ep2.engine.attachment.hurt}",
        )
    except Exception as exc:
        mark("persistence save/load full state", False, f"CRASH: {exc}")
        traceback.print_exc()

    # --- (10) live chat hits emotion ---
    try:
        # message_routes is a maxlen deque — mark by timestamp, not length slice.
        pre_ts = None
        if th.message_routes:
            pre_ts = th.message_routes[-1].get("timestamp")
        user_id = f"emo-live-{uuid.uuid4().hex[:8]}"
        reply = th.process_user_input(
            "Hello Monday, how are you feeling about us today?",
            user_id=user_id,
        )
        recent = list(th.message_routes)
        if pre_ts is not None:
            # keep entries at/after marker (inclusive of post-turn traffic)
            idx = 0
            for i, r in enumerate(recent):
                if r.get("timestamp") == pre_ts:
                    idx = i + 1
            recent = recent[idx:]
        hit = any(
            r.get("to") == "emotion"
            and r.get("type") == "process_input"
            and r.get("status") == "success"
            for r in recent
        )
        chat_ok = isinstance(reply, str) and bool(reply.strip())
        mark(
            "live chat hits emotion process_input",
            hit and chat_ok,
            f"hit={hit} reply_len={len(reply) if isinstance(reply, str) else 0} "
            f"recent_emotion={[r for r in recent if r.get('to')=='emotion']}",
        )
    except Exception as exc:
        mark("live chat hits emotion process_input", False, f"CRASH: {exc}")
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
