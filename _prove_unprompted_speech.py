#!/usr/bin/env python3
"""Prove Thalamus.deliver_unprompted_speech works without a user turn."""
from __future__ import annotations

import tempfile
import time
from pathlib import Path

from autonomous_thinking import AutonomousThought
from direct_notus import DirectNotusProcess
from run_abin import create_core_systems, shutdown_core_systems


def _factory(*, thalamus, runtime_directory):
    return DirectNotusProcess(
        storage_path=str(Path(runtime_directory) / "prove_unprompted.sqlite3"),
        thalamus=thalamus,
    )


def _inject_speak_worthy(autonomous, content: str, intensity: float = 0.92) -> None:
    thought = AutonomousThought(
        id=f"prove_unprompted_{int(time.time() * 1000)}",
        content=content,
        thought_type="feeling",
        trigger="unresolved_prove",
        intensity=intensity,
        speak_worthy=True,
        timestamp=time.time(),
        mode="inner",
        topic_key="prove_unprompted_unique",
    )
    lock = getattr(autonomous, "lock", None)
    queue = getattr(autonomous, "thought_queue", None)
    if queue is None:
        raise RuntimeError("autonomous.thought_queue missing")
    if lock is not None:
        with lock:
            queue.insert(0, thought)
    else:
        queue.insert(0, thought)


def main() -> int:
    results = []
    td = tempfile.mkdtemp(prefix="monday_unprompted_")
    systems = create_core_systems(
        runtime_directory=td,
        notus_factory=_factory,
        enable_autonomous=True,
    )
    try:
        th = systems["thalamus"]
        auto = systems["autonomous"]
        # Clear any leftover cooldown from prior path noise.
        th._last_spoken_aside_time = 0.0
        # Speech interval: allow now.
        speech = systems.get("speech")
        if speech is not None:
            speech.last_speech_time = 0.0
            speech.conversation_active = False
            speech.user_is_typing = False
            speech.user_is_busy = False

        content = "The quiet tonight sits heavy — I noticed it on my own."
        # Pause background minting so the proof exercises OUR forced candidate.
        auto.running = False
        time.sleep(0.05)
        lock = getattr(auto, "lock", None)
        if lock is not None:
            with lock:
                auto.thought_queue.clear()
        else:
            auto.thought_queue.clear()
        for attr in ("_speak_satiation", "_speak_sat_updated", "_topic_reactivated_at"):
            bag = getattr(auto, attr, None)
            if isinstance(bag, dict):
                bag.clear()
        _inject_speak_worthy(auto, content, intensity=0.92)

        first = th.deliver_unprompted_speech(user_id="matthew")
        spoke = bool(first.get("spoke"))
        text = first.get("text")
        results.append(
            (
                "first_spoke",
                spoke and isinstance(text, str) and bool(text.strip()),
                f"reason={first.get('reason')} text={(text or '')[:80]!r}",
            )
        )
        if spoke and isinstance(text, str):
            results.append(
                (
                    "text_from_aside",
                    content.strip() in text or text.strip() == content.strip(),
                    f"got={(text or '')[:100]!r}",
                )
            )

        second = th.deliver_unprompted_speech(user_id="matthew")
        results.append(
            (
                "cooldown_blocks_dump",
                second.get("spoke") is False and second.get("reason") == "cooldown",
                f"reason={second.get('reason')} spoke={second.get('spoke')}",
            )
        )

        # Method exists and works with no user_input (already called that way).
        results.append(
            (
                "api_present",
                callable(getattr(th, "deliver_unprompted_speech", None)),
                "deliver_unprompted_speech",
            )
        )

        # Canned provider strings gone from render terminal path.
        from direct_response import DeterministicResponseProvider

        provider = DeterministicResponseProvider()
        out = provider.render("what is the meaning of life?", {"intent": "question"}, [])
        results.append(
            (
                "provider_no_canned_question",
                out is None,
                repr(out)[:80],
            )
        )
        out2 = provider.render("hello", {"intent": "greeting"}, [])
        results.append(
            (
                "provider_no_canned_hello",
                out2 is None,
                repr(out2)[:80],
            )
        )
        out3 = provider.render("explain gravity", {"intent": "question"}, [])
        results.append(
            (
                "provider_no_canned_gravity",
                out3 is None
                or (
                    isinstance(out3, str)
                    and not out3.lower().startswith("gravity is the force")
                ),
                repr(out3)[:80],
            )
        )

    finally:
        shutdown_core_systems(systems)

    print("UNPROMPTED SPEECH PROOF")
    print("=======================")
    failed = 0
    for name, ok, detail in results:
        flag = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"{flag}: {name} — {detail}")
    print(
        f"SUMMARY: {'PASS' if failed == 0 else 'FAIL'} — "
        f"{len(results) - failed}/{len(results)}"
    )
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
