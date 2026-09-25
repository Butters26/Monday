#!/usr/bin/env python3
"""Prove remaining full-bar honesty/mechanism fixes (Emotion excluded; Learning ignored)."""
from __future__ import annotations

import tempfile
from pathlib import Path

from direct_notus import DirectNotusProcess
from run_abin import create_core_systems, shutdown_core_systems


def _factory(*, thalamus, runtime_directory):
    return DirectNotusProcess(
        storage_path=str(Path(runtime_directory) / "prove_notus.sqlite3"),
        thalamus=thalamus,
    )


def main() -> int:
    results = []
    td = tempfile.mkdtemp(prefix="monday_full_bar_")
    systems = create_core_systems(
        runtime_directory=td,
        notus_factory=_factory,
        enable_autonomous=False,
    )
    try:
        # 1. Mocks detached
        ok = (
            "continuous_thought_generator" not in systems
            and "controlled_thinking" not in systems
            and systems["meta_awareness"].spontaneous_system is None
            and systems["meta_awareness"].controlled_system is None
        )
        results.append(("mocks_detached", ok, "CTG/CT not in create_core_systems"))

        env = systems["meta_awareness"].observe_turn(
            user_input="hello there",
            understanding={"intent": "greeting"},
            intensity=0.4,
            novelty_score=0.2,
            user_id="prove",
        )
        # envelope may nest extras
        fed = env.get("controlled_fed")
        if fed is None and isinstance(env.get("content"), dict):
            fed = env["content"].get("controlled_fed")
        attached = env.get("controlled_generator_attached")
        if attached is None and isinstance(env.get("content"), dict):
            attached = env["content"].get("controlled_generator_attached")
        results.append(
            (
                "meta_no_false_fed",
                fed is False and attached is False,
                f"fed={fed} attached={attached}",
            )
        )

        # 2. Speech decision-only
        sp = systems["speech"].process_message({"type": "get_pending_speech"})
        results.append(
            (
                "speech_pending_removed",
                sp.get("status") == "error" and sp.get("decision_only") is True,
                str(sp.get("message", ""))[:80],
            )
        )
        ev = systems["speech"].process_message(
            {
                "type": "evaluate_thought",
                "thought": {
                    "id": "t1",
                    "content": "I noticed the sky",
                    "thought_type": "observation",
                    "intensity": 0.8,
                },
            }
        )
        results.append(
            (
                "speech_evaluate_live",
                ev.get("status") == "success" and "decision" in ev,
                str(ev.get("decision", {}).get("should_speak")),
            )
        )

        # 3. Conversation dead poll
        conv = systems["conversation"].process_message(
            {"type": "check_unprompted_speech", "content": {}}
        )
        results.append(
            (
                "conversation_poll_removed",
                conv.get("status") == "error" and conv.get("has_speech") is False,
                str(conv.get("message", ""))[:80],
            )
        )

        # 4. Novelty score-only
        nov = systems["novelty"].process_message(
            {"type": "get_pending_questions", "content": {}}
        )
        results.append(
            (
                "novelty_pending_removed",
                nov.get("status") == "error",
                str(nov.get("message", ""))[:80],
            )
        )
        assess = systems["novelty"].assess_experience(
            text="a purple quantum bagel appeared", source="proof", commit=True
        )
        results.append(
            (
                "novelty_score_works",
                isinstance(assess.get("novelty_score"), (int, float)),
                f"score={assess.get('novelty_score')}",
            )
        )

        # 5. SharedRepresentation co-occurrence producer
        sr = systems["shared_representation"].process_message(
            {
                "type": "resolve_from_text",
                "content": {
                    "text": "monday drinks dark roast coffee",
                    "user_id": "prove",
                },
            }
        )
        results.append(
            (
                "shared_rep_edges",
                int(sr.get("co_occurrence_edges_added") or 0) > 0
                and bool(sr.get("spread_had_edges")),
                f"added={sr.get('co_occurrence_edges_added')} edges={sr.get('relationship_edges')}",
            )
        )

        # 6. Reasoning rename + persist noop
        from reasoning import ReasoningLobe, MaximumSophisticationReasoning

        results.append(
            (
                "reasoning_alias",
                ReasoningLobe is MaximumSophisticationReasoning,
                type(systems["reasoning"]).__name__,
            )
        )
        adapter = systems["reasoning"]
        reasoner = None
        for attr in ("reasoner", "_reasoner", "lobe", "mind", "reasoning"):
            cand = getattr(adapter, attr, None)
            if cand is not None and hasattr(cand, "_save_persistent_state_to_memory"):
                reasoner = cand
                break
        if reasoner is None:
            # DirectReasoningAdapter may construct per-call; probe class methods
            from reasoning import ReasoningLobe
            reasoner = ReasoningLobe(thalamus=systems["thalamus"])
        detail = type(reasoner).__name__
        reasoner._save_persistent_state_to_memory()
        reasoner._load_persistent_state_from_memory()
        results.append(("reasoning_persist_noop", True, detail))

        # 7. Language no NO TEMPLATES / no check_knowledge call path
        import language_generation as lg
        import inspect

        src = inspect.getsource(lg.GrammarEngine._compose_uncertainty)
        results.append(
            (
                "language_no_templates_claim",
                "NO TEMPLATES" not in src
                and "'type': 'check_knowledge'" not in src
                and '"type": "check_knowledge"' not in src,
                "GrammarEngine._compose_uncertainty scrubbed",
            )
        )

        # 8. Output TTS-off
        out = systems["output"]
        tts_off = (
            getattr(out, "tts_engine", None) is None
            or getattr(out, "tts_available", False) is False
        )
        results.append(
            (
                "output_tts_off",
                tts_off,
                f"tts_available={getattr(out, 'tts_available', None)} engine={getattr(out, 'tts_engine', None)}",
            )
        )

        # 9. Voice status honesty
        vs = systems["voice"].get_status()
        results.append(
            (
                "voice_stub_labeled",
                vs.get("synth_kind") == "formant_sine_stub"
                or "formant" in str(vs).lower()
                or vs.get("nasality_unused") is True,
                str({k: vs.get(k) for k in ("synth_kind", "nasality_unused", "vibrato_unused")}),
            )
        )

        # 10. Notus fallback present
        th = systems["thalamus"]
        results.append(
            (
                "notus_fallback_wired",
                hasattr(th, "notus_fallback")
                and hasattr(th, "retry_unsaved_notus_records"),
                "thalamus.notus_fallback",
            )
        )

        # 11. Prompted path still answers
        reply = th.process_user_input("Hi Monday, my favorite color is teal", user_id="prove")
        results.append(
            (
                "prompted_path_reply",
                isinstance(reply, str) and len(reply.strip()) > 0,
                (reply or "")[:100],
            )
        )

    finally:
        shutdown_core_systems(systems)

    print("FULL-BAR REMAINING PROOF")
    print("========================")
    failed = 0
    for name, ok, detail in results:
        flag = "PASS" if ok else "FAIL"
        if not ok:
            failed += 1
        print(f"{flag}: {name} — {detail}")
    print(f"SUMMARY: {'PASS' if failed == 0 else 'FAIL'} — {len(results)-failed}/{len(results)}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
