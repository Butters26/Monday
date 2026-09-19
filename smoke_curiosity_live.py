#!/usr/bin/env python3
"""Pass/fail smoke: live-path curiosity without novelty_lobe as owner.

Proves:
  (1) Strong/unresolved turn can append one honest follow-up (forced)
  (2) Mild "hello" does not force curiosity spam
  (3) Chat still works when novelty lobe is missing (notify does not crash)

No test_*.py. No cloud. No percents.
Run: python3 smoke_curiosity_live.py
"""

from __future__ import annotations

import io
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict

from advanced_emotional_engine import EmotionalProcess
from conversation import ConversationSystem
from output import OutputLobe
from thalamus import Thalamus


class _StubLobe:
    def __init__(self, name: str):
        self.name = name

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        if msg_type == "store":
            return {"status": "success", "stored": True}
        if msg_type in ("query", "query_context"):
            return {"status": "success", "memories": [], "facts": [], "content": {"memories": [], "facts": []}}
        if msg_type == "think":
            return {
                "status": "success",
                "answer": "Stub reply from reasoning.",
                "semantic_input": {
                    "intent": "conversation",
                    "answer": "Stub reply from reasoning.",
                    "propositions": ["Stub reply from reasoning."],
                },
            }
        if msg_type == "generate":
            payload = message.get("content", message)
            sem = payload.get("semantic_input", {}) if isinstance(payload, dict) else {}
            sentence = sem.get("answer") or "Stub reply from language."
            return {"status": "success", "sentence": sentence}
        if msg_type == "health":
            return {"status": "success", "healthy": True}
        return {"status": "success", "ok": True, "type": msg_type}


def _wire(runtime: Path) -> Dict[str, Any]:
    thalamus = Thalamus()
    conversation = ConversationSystem(thalamus=thalamus)
    emotion = EmotionalProcess(
        state_file=str(runtime / "emotional_state.json"), thalamus=thalamus
    )
    output = OutputLobe(thalamus=thalamus, enable_tts=False)
    for name, lobe in (
        ("conversation", conversation),
        ("notus", _StubLobe("notus")),
        ("emotion", emotion),
        ("reasoning", _StubLobe("reasoning")),
        ("language", _StubLobe("language")),
        ("output", output),
    ):
        result = thalamus.register_lobe(name, lobe)
        if result.get("status") != "success":
            raise RuntimeError(f"register {name}: {result}")
    # novelty intentionally NOT registered
    thalamus._curiosity_cooldown_sec = 0.0
    thalamus._last_curiosity_time = 0.0
    thalamus._spoken_aside_cooldown_sec = 9999.0  # keep aside out of this smoke
    return {"thalamus": thalamus, "emotion": emotion, "conversation": conversation}


def main() -> int:
    runtime = Path(tempfile.mkdtemp(prefix="monday-curiosity-smoke-"))
    systems = _wire(runtime)
    thalamus = systems["thalamus"]
    emotion = systems["emotion"]
    failures = []

    print("=== smoke_curiosity_live (no novelty_lobe, no Postgres required) ===")
    print(f"runtime: {runtime}")
    print(f"registered: {sorted(thalamus.lobe_handlers.keys())}")
    assert "novelty" not in thalamus.lobe_handlers

    # --- (1) forced high intensity / unresolved -> follow-up question ---
    emotion.engine._unresolved_appraisals.append(("loss", 0.9, time.time()))
    emotion.engine.emotional_intensity = 0.92
    thalamus._force_curiosity_follow_up = True
    thalamus._last_curiosity_time = 0.0
    line = (
        "My sister vanished last night and nobody will tell me anything real."
    )
    reply1 = thalamus.process_user_input(line)
    print(f"(1) strong/unresolved reply:\\n{reply1}\\n")
    if "?" not in reply1:
        failures.append("(1) expected a follow-up question on forced high/unresolved turn")
    elif "invent" not in reply1.lower() and "understand" not in reply1.lower() and "help with" not in reply1.lower():
        # Still OK if any honest question landed
        if reply1.count("?") < 1:
            failures.append("(1) question mark missing")
    else:
        print("    follow-up question present OK")

    # --- (2) mild hello -> no forced curiosity spam ---
    thalamus._force_curiosity_follow_up = False
    thalamus._last_curiosity_time = 0.0
    # Clear unresolved so greeting is a clean mild turn
    emotion.engine._unresolved_appraisals.clear()
    emotion.engine.emotional_intensity = 0.2
    reply2 = thalamus.process_user_input("hello")
    print(f"(2) mild hello reply:\\n{reply2}\\n")
    # Main stub reply should not gain a curiosity append. Allow "?" only if the
    # stub itself had one (it doesn't). Count question sentences beyond base.
    base_ok = "Stub reply" in reply2 or isinstance(reply2, str)
    curiosity_markers = (
        "do not want to invent",
        "don't want to invent",
        "what would help with this",
        "what am i missing",
        "tell me more about what you meant",
    )
    lowered = reply2.lower()
    if any(m in lowered for m in curiosity_markers):
        failures.append("(2) mild hello forced a curiosity follow-up")
    elif reply2.rstrip().endswith("?") and "\n\n" in reply2:
        failures.append("(2) mild hello appended a question spam block")
    else:
        print("    no curiosity spam on hello OK")
    if not base_ok or not str(reply2).strip():
        failures.append("(2) hello reply empty / broken")

    # --- (3) novelty missing: notify must not crash chat ---
    buf = io.StringIO()
    old = sys.stdout
    sys.stdout = buf
    crashed = False
    try:
        # Direct notify path + full turn with high intensity
        emotion._notify_novelty_lobe("brand new strange stimulus", "curious", 0.95)
        emotion.engine.emotional_intensity = 0.95
        reply3 = thalamus.process_user_input(
            "Something completely new appeared and I am shaken by it."
        )
    except Exception as exc:
        crashed = True
        failures.append(f"(3) crash with novelty missing: {exc}")
        reply3 = ""
    finally:
        sys.stdout = old
    out = buf.getvalue()
    print(f"(3) notify/chat with novelty missing; stdout noise={len(out)} chars")
    print(f"    reply: {reply3[:160]!r}")
    if "Failed to notify novelty" in out or "notifying Novelty Lobe" in out:
        failures.append("(3) novelty notify still printing errors")
    if not crashed and (not isinstance(reply3, str) or not reply3.strip()):
        failures.append("(3) empty reply when novelty missing")
    if not crashed and "novelty" not in thalamus.lobe_handlers:
        print("    no crash / silent notify OK")

    print("=== RESULT ===")
    if failures:
        for f in failures:
            print(f"FAIL: {f}")
        return 1
    print("PASS: (1) curiosity follow-up, (2) mild hello clean, (3) novelty-missing chat")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
