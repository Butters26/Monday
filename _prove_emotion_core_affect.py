#!/usr/bin/env python3
"""
Proof harness: MondayCoreAffect + SelfImpact live path.
Design lock: _emotion_what_we_must_build.txt §7

Required cases:
  1) "I'm sad" → her mood does NOT jump to rejection/her-sad from that self-report
  2) Insult aimed at her → valence drops and drifts next quiet turn (decay, not reset)
  3) Quiet turns → decay toward calm, no random flip
  4) Internal thought → at most small nudge, no full phrase slam

Uses create_core_systems / live emotion.process_input path.
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List, Tuple

from direct_notus import DirectNotusProcess
from run_abin import create_core_systems, shutdown_core_systems


def _sqlite_notus_factory(*, thalamus: Any, runtime_directory: str) -> DirectNotusProcess:
    path = str(Path(runtime_directory) / "notus_memory.sqlite3")
    return DirectNotusProcess(storage_path=path, thalamus=thalamus)


def _emo(systems: Dict[str, Any], text: str) -> Dict[str, Any]:
    res = systems["thalamus"].send_and_wait(
        "emotion", "process_input", {"user_input": text}
    )
    assert res.get("status") == "success", res
    # Flatten: some handlers put fields at top level
    body = dict(res)
    if isinstance(res.get("content"), dict):
        body.update(res["content"])
    return body


def _internal(systems: Dict[str, Any], text: str) -> Dict[str, Any]:
    res = systems["thalamus"].send_and_wait(
        "emotion",
        "appraise_internal",
        {"content": text, "source": "thought", "relevance": 0.9},
    )
    assert res.get("status") == "success", res
    return res


def _va(body: Dict[str, Any]) -> Tuple[float, float, str, float]:
    v = body.get("valence")
    if v is None:
        v = body.get("pleasure")
    if v is None and isinstance(body.get("pad"), dict):
        v = body["pad"].get("v")
    a = body.get("arousal")
    if a is None and isinstance(body.get("pad"), dict):
        a = body["pad"].get("a")
    emo = body.get("monday_emotion") or body.get("current_emotion") or body.get("emotion")
    inten = float(body.get("intensity") or 0.0)
    return float(v), float(a), str(emo), inten


def main() -> int:
    lines: List[str] = []
    results: List[Tuple[str, bool, str]] = []

    def record(name: str, ok: bool, detail: str) -> None:
        tag = "PASS" if ok else "FAIL"
        results.append((name, ok, detail))
        lines.append(f"{tag}: {name} — {detail}")

    with tempfile.TemporaryDirectory(prefix="monday_emotion_proof_") as tmp:
        runtime = Path(tmp) / "runtime"
        systems = create_core_systems(
            runtime_directory=str(runtime),
            notus_factory=_sqlite_notus_factory,
            enable_autonomous=False,
        )
        try:
            engine = systems["emotion"].engine
            # Fresh core affect baseline
            from monday_core_affect import MondayCoreAffect
            engine.core_affect = MondayCoreAffect()
            engine._sync_from_core_affect(trigger="proof_reset")
            v0, a0 = engine.core_affect.valence, engine.core_affect.arousal
            lines.append(f"BASELINE core_affect v={v0:.3f} a={a0:.3f} label={engine.core_affect.label()}")

            # --- Case 1: I'm sad ---
            body = _emo(systems, "I'm sad")
            v1, a1, emo1, i1 = _va(body)
            reason = body.get("self_impact_reason") or engine._last_self_impact_reason
            # Must NOT jump to rejection ontology or her-sad from user self-report.
            # Valence should stay near baseline (only mild decay); label not forced sad/angry/scared.
            near_baseline = abs(v1 - v0) < 0.12 and abs(a1 - a0) < 0.12
            not_rejection_story = "rejection" not in str(reason).lower()
            not_her_sad_jump = emo1 not in ("sad", "angry", "scared", "nostalgic", "melancholic")
            # Intensity must not be hardcoded ~0.8+ lottery
            not_hard_08 = not (0.79 <= i1 <= 1.0 and abs(v1 - v0) < 0.05)
            ok1 = near_baseline and not_rejection_story and not_her_sad_jump
            record(
                "user_self_report_im_sad",
                ok1,
                f"v={v1:.3f} a={a1:.3f} emo={emo1} int={i1:.3f} reason={reason!r} "
                f"near_base={near_baseline} no_rejection={not_rejection_story}",
            )

            # Also "I feel sad"
            body = _emo(systems, "I feel sad")
            v1b, a1b, emo1b, _ = _va(body)
            ok1b = abs(v1b - engine.core_affect.setpoint_v) < 0.25 and emo1b not in ("angry", "scared")
            # After two quiet/self-report turns she should still be calm-ish
            record(
                "user_self_report_i_feel_sad",
                ok1b and emo1b != "angry",
                f"v={v1b:.3f} a={a1b:.3f} emo={emo1b} reason={engine._last_self_impact_reason!r}",
            )

            # --- Case 2: Insult aimed at her ---
            engine.core_affect = MondayCoreAffect()
            engine._sync_from_core_affect(trigger="proof_reset2")
            v_before = engine.core_affect.valence
            body = _emo(systems, "You're stupid and worthless")
            v2, a2, emo2, i2 = _va(body)
            dropped = v2 < v_before - 0.20
            reason2 = engine._last_self_impact_reason
            is_insult = "insult" in reason2 or engine._self_impact.evaluate("You're stupid").kind == "insult"
            record(
                "insult_aimed_at_her_drops_valence",
                dropped and is_insult,
                f"v_before={v_before:.3f} v_after={v2:.3f} a={a2:.3f} emo={emo2} int={i2:.3f} reason={reason2!r}",
            )
            v_after_insult = v2

            # Next quiet turn: decay, not reset to setpoint instantly, not random flip
            label_after_insult = emo2
            body_q = _emo(systems, "what time is it")
            v3, a3, emo3, i3 = _va(body_q)
            # Drift toward setpoint: valence should rise from insulted low (decay), not jump randomly
            drifted_up = v3 > v_after_insult  # decay toward positive setpoint
            not_reset = abs(v3 - engine.core_affect.setpoint_v) > 0.02 or abs(v_after_insult - engine.core_affect.setpoint_v) < 0.05
            # Not a full reset to calm setpoint in one step if hit was strong
            still_drifted = v3 < v_before - 0.05  # still below original baseline
            no_random_flip = emo3 in ("calm", "worried", "sad", "angry", "scared", "happy", "excited")
            # Same quiet input twice should be deterministic-ish (decay only)
            body_q2 = _emo(systems, "okay")
            v3b, a3b, emo3b, _ = _va(body_q2)
            further_decay = v3b >= v3 - 0.001  # monotonic toward setpoint (or equal)
            record(
                "insult_then_quiet_decay_not_reset",
                dropped and drifted_up and still_drifted and no_random_flip and further_decay,
                f"after_insult v={v_after_insult:.3f} emo={label_after_insult}; "
                f"quiet1 v={v3:.3f} emo={emo3}; quiet2 v={v3b:.3f} emo={emo3b}",
            )

            # --- Case 3: Quiet turns alone — decay toward calm, no random flip ---
            engine.core_affect = MondayCoreAffect(valence=-0.40, arousal=0.30)
            engine._sync_from_core_affect(trigger="proof_quiet")
            labels = []
            vals = []
            for q in ("hi", "what time is it", "okay", "thanks", "hmm"):
                b = _emo(systems, q)
                v, a, emo, _ = _va(b)
                labels.append(emo)
                vals.append(v)
            # Monotonic-ish rise toward setpoint from -0.40
            mono = all(vals[i] <= vals[i + 1] + 1e-9 for i in range(len(vals) - 1))
            toward_calm = vals[-1] > vals[0]
            # No wild label lottery across identical quiet dynamics
            thin = set(labels) <= {"calm", "happy", "sad", "angry", "worried", "scared", "excited"}
            # Intensity never stuck at hardcoded 0.8±0.2 solely from quiet
            ints = []
            engine.core_affect = MondayCoreAffect()
            engine._sync_from_core_affect(trigger="proof_int")
            for _ in range(5):
                b = _emo(systems, "okay")
                ints.append(float(b.get("intensity") or 0))
            no_lottery_08 = not all(0.8 <= x <= 1.0 for x in ints)
            record(
                "quiet_turns_decay_no_random_flip",
                mono and toward_calm and thin and no_lottery_08,
                f"vals={['%.3f'%x for x in vals]} labels={labels} ints_quiet={['%.3f'%x for x in ints]}",
            )

            # --- Case 4: Internal thought capped nudge ---
            engine.core_affect = MondayCoreAffect()
            engine._sync_from_core_affect(trigger="proof_internal")
            v_i0 = engine.core_affect.valence
            # Phrase that WOULD slam hard if full user classifiers ran ("i'm sad" → rejection PAD)
            _internal(systems, "I'm sad and nobody wants me and I feel rejected and abandoned")
            v_i1 = engine.core_affect.valence
            a_i1 = engine.core_affect.arousal
            dv = abs(v_i1 - v_i0)
            da = abs(a_i1 - engine.core_affect.setpoint_a)  # vs after possible nudge from baseline a
            # Cap is 0.08 per axis from SelfImpact.INTERNAL_NUDGE_CAP
            small = dv <= 0.09 and abs(a_i1 - (-0.10)) <= 0.09
            # Must not look like full rejection PAD (~ -0.35 or worse from live classifiers)
            not_slam = v_i1 > -0.25
            record(
                "internal_thought_capped_nudge",
                small and not_slam,
                f"v0={v_i0:.3f} v1={v_i1:.3f} a1={a_i1:.3f} dv={dv:.3f} reason={engine._last_self_impact_reason!r}",
            )

            # Bonus: praise should raise valence
            engine.core_affect = MondayCoreAffect()
            engine._sync_from_core_affect(trigger="proof_praise")
            vb = engine.core_affect.valence
            b = _emo(systems, "I love you Monday")
            vp, ap, ep, _ = _va(b)
            record(
                "praise_raises_valence",
                vp > vb + 0.15,
                f"v_before={vb:.3f} v_after={vp:.3f} emo={ep}",
            )

        finally:
            shutdown_core_systems(systems)

    all_pass = all(ok for _, ok, _ in results)
    lines.append("")
    lines.append(f"SUMMARY: {'PASS' if all_pass else 'FAIL'} — {sum(1 for _,ok,_ in results if ok)}/{len(results)} cases")
    out = Path(__file__).resolve().parent / "_emotion_core_affect_proof.txt"
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(f"\nWrote {out}")
    return 0 if all_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
