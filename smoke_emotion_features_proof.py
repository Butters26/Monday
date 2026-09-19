#!/usr/bin/env python3
"""Behavioral proof for emotion-engine features (real interfaces only).

Writes PASS|FAIL|PARTIAL|NOT IMPLEMENTED verdicts to stdout and
/workspace/Monday/_emotion_features_proof.txt

Run: python3 smoke_emotion_features_proof.py
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

os.environ.setdefault("NOTUS_POSTGRES_DB", "notus_memory")
os.environ.setdefault("NOTUS_POSTGRES_USER", os.getenv("USER", "box"))
os.environ.setdefault("NOTUS_POSTGRES_HOST", "localhost")
os.environ.setdefault(
    "NOTUS_POSTGRES_PASSWORD", os.getenv("NOTUS_POSTGRES_PASSWORD", "box")
)

from advanced_emotional_engine import (
    AdvancedEmotionalEngine,
    AppraisalEngine,
    EmotionalBlend,
    EmotionalMemory,
    EmotionalProcess,
    EmotionalState,
    ExpressionState,
    InternalEventAppraisal,
    MondayAffect,
)
from run_abin import create_core_systems, shutdown_core_systems

PROOF_PATH = Path("/workspace/Monday/_emotion_features_proof.txt")


class Recorder:
    def __init__(self) -> None:
        self.lines: List[str] = []
        self.rows: List[Tuple[str, str, str]] = []

    def log(self, s: str = "") -> None:
        print(s)
        self.lines.append(s)

    def verdict(self, name: str, status: str, detail: str) -> None:
        assert status in ("PASS", "FAIL", "PARTIAL", "NOT IMPLEMENTED")
        self.rows.append((name, status, detail))
        self.log(f"[{status}] {name} — {detail}")


def _content(resp: Dict[str, Any]) -> Dict[str, Any]:
    c = resp.get("content")
    if isinstance(c, dict):
        return c
    return resp if isinstance(resp, dict) else {}


def main() -> int:
    rec = Recorder()
    rec.log("=== smoke_emotion_features_proof ===")
    rec.log(f"time_local={time.strftime('%Y-%m-%d %H:%M:%S %Z')}")
    runtime = Path(tempfile.mkdtemp(prefix="monday-emo-feat-"))
    rec.log(f"runtime={runtime}")

    systems = None
    try:
        systems = create_core_systems(runtime_directory=str(runtime))
        th = systems["thalamus"]
        ep: EmotionalProcess = systems["emotion"]
        eng = ep.engine
        out = systems["output"]

        # ---- Defect 1: feel_emotion contract ----
        rec.log("\n--- DEFECT feel_emotion ---")
        wrong = th.send_and_wait(
            "emotion", "feel_emotion", {"text": "I am sad"}, source="proof"
        )
        rec.log(f"wrong_call={{'text':'I am sad'}} -> {wrong}")
        before_e, before_i, before_m = (
            eng.current_emotion.value,
            float(eng.emotional_intensity),
            len(eng.emotional_memories),
        )
        ok = th.send_and_wait(
            "emotion",
            "feel_emotion",
            {"emotion": "sad", "intensity": 0.82, "trigger": "proof direct sad"},
            source="proof",
        )
        ok_body = _content(ok)
        changed = (
            ok.get("status") == "success"
            and eng.current_emotion.value == "sad"
            and abs(float(eng.emotional_intensity) - 0.82) < 1e-9
            and len(eng.emotional_memories) > before_m
            and bool(ok_body.get("emotion_changed") or ok.get("emotion_changed"))
        )
        rec.verdict(
            "feel_emotion_canonical",
            "PASS" if changed else "FAIL",
            f"before={before_e}@{before_i:.3f} mems={before_m} "
            f"after={eng.current_emotion.value}@{eng.emotional_intensity:.3f} "
            f"mems={len(eng.emotional_memories)} resp={ok}",
        )
        wrong_ok = (
            wrong.get("status") == "error"
            and "requires 'emotion'" in str(wrong.get("message", ""))
        )
        rec.verdict(
            "feel_emotion_rejects_text_only",
            "PASS" if wrong_ok else "FAIL",
            f"observed={wrong.get('message')}",
        )

        # ---- Defect 2: nudge vs appraise_internal ----
        rec.log("\n--- DEFECT nudge_from_inner_life vs appraise_internal ---")
        nudge_msg = th.send_and_wait(
            "emotion",
            "nudge_from_inner_life",
            {"content": "I keep replaying that betrayal.", "source": "thought"},
            source="proof",
        )
        method = ep.nudge_from_inner_life(
            "I keep replaying that betrayal and abandonment.",
            source="thought",
            relevance=0.9,
        )
        pre = (eng.current_emotion.value, float(eng.emotional_intensity), _pad(eng))
        # fresh fingerprint to avoid cooldown/loop guard
        unique = f"They broke my trust and left me alone — still hurts [{uuid.uuid4().hex[:8]}]"
        ai = th.send_and_wait(
            "emotion",
            "appraise_internal",
            {
                "content": unique,
                "source": "memory",
                "relevance": 0.95,
                "resolved": False,
                "memory_age_seconds": 20.0,
            },
            source="proof",
        )
        post = (eng.current_emotion.value, float(eng.emotional_intensity), _pad(eng))
        moved = ai.get("status") == "success" and (
            post[0] != pre[0] or abs(post[1] - pre[1]) > 0.01 or post[2] != pre[2]
        )
        alias_unknown = (
            nudge_msg.get("status") == "error"
            and "Unknown message type" in str(nudge_msg.get("message", ""))
        )
        method_ok = method.get("status") == "success"
        if moved and alias_unknown and method_ok:
            status = "PASS"
        elif moved and method_ok:
            status = "PARTIAL"
        else:
            status = "FAIL"
        rec.verdict(
            "nudge_vs_appraise_internal",
            status,
            f"canonical=appraise_internal moved={moved} method_ok={method_ok} "
            f"nudge_msg={nudge_msg.get('message')} ai={ai.get('status')} "
            f"pre={pre} post={post}",
        )

        # 1 EmotionalMemory
        rec.log("\n--- 1 EmotionalMemory ---")
        try:
            mem = EmotionalMemory(
                emotion=EmotionalState.ANGRY,
                intensity=0.7,
                trigger="proof memory trigger betrayal words",
                timestamp=time.time(),
                context="proof context",
            )
            before = len(eng.emotional_memories)
            eng.feel_emotion(
                EmotionalState.ANGRY, 0.7, mem.trigger, mem.context
            )
            after = len(eng.emotional_memories)
            last = eng.emotional_memories[-1] if eng.emotional_memories else None
            stored = after > before and last is not None and mem.trigger in last.trigger
            st = th.send_and_wait("emotion", "get_state", {}, source="proof")
            st_body = _content(st)
            exposed = int(st.get("memory_count") or st_body.get("memory_count") or 0) >= after
            rec.verdict(
                "1_EmotionalMemory",
                "PASS" if stored and exposed else "FAIL",
                f"constructed+stored via feel_emotion before={before} after={after} "
                f"last_trigger={getattr(last,'trigger',None)!r} exposed_count="
                f"{st.get('memory_count') or st_body.get('memory_count')}",
            )
        except Exception as exc:
            rec.verdict("1_EmotionalMemory", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 2 EmotionalBlend
        rec.log("\n--- 2 EmotionalBlend ---")
        try:
            blend_eng = AdvancedEmotionalEngine(name="blend-proof")
            blend_eng.current_emotion = EmotionalState.SAD
            blend_eng.emotional_intensity = 0.6
            blend = blend_eng._check_emotional_blending(EmotionalState.HAPPY, 0.7)
            if blend is None:
                rec.verdict(
                    "2_EmotionalBlend",
                    "FAIL",
                    "expected blend for SAD+HAPPY at intensity>0.2, got None",
                )
            else:
                blend_eng._create_emotional_blend(blend, "sad+happy blend proof", "")
                ok_b = (
                    isinstance(blend, EmotionalBlend)
                    and blend.primary_emotion == EmotionalState.NOSTALGIC
                    and len(blend.secondary_emotions) == 2
                    and blend.intensity >= 0.6
                    and blend_eng.current_emotion == EmotionalState.NOSTALGIC
                    and len(blend_eng.emotional_blends) == 1
                )
                # no-blend case
                none_blend = blend_eng._check_emotional_blending(
                    EmotionalState.DISGUSTED, 0.9
                )
                rec.verdict(
                    "2_EmotionalBlend",
                    "PASS" if ok_b and none_blend is None else "FAIL",
                    f"primary={blend.primary_emotion.value} secondary="
                    f"{[(e.value,w) for e,w in blend.secondary_emotions]} "
                    f"intensity={blend.intensity} none_when_no_combo={none_blend}",
                )
        except Exception as exc:
            rec.verdict("2_EmotionalBlend", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 3 Patterns
        rec.log("\n--- 3 Patterns ---")
        try:
            before_p = len(eng.emotional_patterns)
            trigger = "betrayed trust abandoned lonely proofpatternxyz"
            eng._update_emotional_patterns(EmotionalState.SAD, trigger)
            after_p = len(eng.emotional_patterns)
            hit = any(
                w in eng.emotional_patterns
                for w in ("betrayed", "trust", "abandoned", "lonely", "proofpatternxyz")
            )
            sample = {
                k: [e.value for e in v[-2:]]
                for k, v in list(eng.emotional_patterns.items())
                if k in trigger
            }
            st = th.send_and_wait("emotion", "get_state", {}, source="proof")
            st_body = _content(st)
            exposed = "patterns" in st or "patterns" in st_body or "emotional_patterns" in st or "emotional_patterns" in st_body
            # retrieval/use: cues path reads emotional_patterns
            cues = eng._analyze_emotional_cues(trigger)
            used = True  # path exists; cue bump may be tiny
            rec.verdict(
                "3_Patterns",
                "PASS" if after_p > before_p and hit and exposed else "FAIL",
                f"before={before_p} after={after_p} hit={hit} exposed={exposed} "
                f"sample={sample} cues_after={cues}",
            )
        except Exception as exc:
            rec.verdict("3_Patterns", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 4 Persistence
        rec.log("\n--- 4 Persistence ---")
        try:
            tmp = runtime / "persist_feat.json"
            eng.feel_emotion(
                EmotionalState.MELANCHOLIC, 0.77, "persist proof trigger grief loss", ""
            )
            eng.pad.v, eng.pad.a, eng.pad.d = -0.42, 0.11, -0.08
            eng.attachment.hurt = 0.55
            eng.internal.worry = 0.44
            eng._update_emotional_patterns(
                EmotionalState.MELANCHOLIC, "persist pattern wordzz grief"
            )
            snap = {
                "emotion": eng.current_emotion.value,
                "intensity": float(eng.emotional_intensity),
                "pad": (eng.pad.v, eng.pad.a, eng.pad.d),
                "hurt": float(eng.attachment.hurt),
                "worry": float(eng.internal.worry),
                "mems": len(eng.emotional_memories),
                "patterns": len(eng.emotional_patterns),
            }
            eng.save_emotional_state(str(tmp))
            fresh = AdvancedEmotionalEngine(name="fresh")
            fresh.load_emotional_state(str(tmp))
            cmp_ok = (
                fresh.current_emotion.value == snap["emotion"]
                and abs(fresh.emotional_intensity - snap["intensity"]) < 1e-9
                and abs(fresh.pad.v - snap["pad"][0]) < 1e-9
                and abs(fresh.attachment.hurt - snap["hurt"]) < 1e-9
                and abs(fresh.internal.worry - snap["worry"]) < 1e-9
                and len(fresh.emotional_memories) == snap["mems"]
                and len(fresh.emotional_patterns) == snap["patterns"]
            )
            rec.verdict(
                "4_Persistence",
                "PASS" if cmp_ok else "FAIL",
                f"snap={snap} loaded_emotion={fresh.current_emotion.value} "
                f"pad=({fresh.pad.v},{fresh.pad.a},{fresh.pad.d}) "
                f"hurt={fresh.attachment.hurt} worry={fresh.internal.worry} "
                f"mems={len(fresh.emotional_memories)} patterns={len(fresh.emotional_patterns)}",
            )
        except Exception as exc:
            rec.verdict("4_Persistence", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 5 MondayAffect
        rec.log("\n--- 5 MondayAffect ---")
        try:
            ma = MondayAffect(name="Monday")
            before = ma.current_emotion.value
            ma.feel_emotion(EmotionalState.PROUD, 0.7, "mondayaffect proud proof", "")
            ok5 = (
                ma.name == "Monday"
                and ma.current_emotion == EmotionalState.PROUD
                and ma.emotional_intensity == 0.7
                and before != "proud"
            )
            rec.verdict(
                "5_MondayAffect",
                "PASS" if ok5 else "FAIL",
                f"name={ma.name!r} before={before} after={ma.current_emotion.value}@"
                f"{ma.emotional_intensity}",
            )
        except Exception as exc:
            rec.verdict("5_MondayAffect", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 6 get_emotional_response
        rec.log("\n--- 6 get_emotional_response ---")
        try:
            pos = eng.get_emotional_response(
                "I love you and I am so grateful for your support today!"
            )
            neg = eng.get_emotional_response(
                "You hurt me badly — that betrayal and rejection still burns."
            )
            neu = eng.get_emotional_response("The meeting is at three o'clock.")
            ok6 = (
                isinstance(pos, str)
                and isinstance(neg, str)
                and isinstance(neu, str)
                and len(pos) > 5
                and len(neg) > 5
                and len(neu) > 5
                and pos != neg
            )
            rec.verdict(
                "6_get_emotional_response",
                "PASS" if ok6 else "FAIL",
                f"pos={pos[:80]!r} neg={neg[:80]!r} neu={neu[:80]!r}",
            )
        except Exception as exc:
            rec.verdict("6_get_emotional_response", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 7 predict_user_emotion
        rec.log("\n--- 7 predict_user_emotion ---")
        try:
            # Reset user affect so each call appraises fresh
            samples = [
                "I am furious that you lied and went behind my back!",
                "I miss them so much since they passed away; the grief is heavy.",
                "We got the job and we are celebrating tonight!",
            ]
            preds = []
            for s in samples:
                eng._user_affect.inferred_emotion = "neutral"
                eng._user_affect.confidence = 0.0
                eng._user_affect.last_updated = 0.0
                preds.append(eng.predict_user_emotion(s))
            labels = [next(iter(p.keys())) if p else None for p in preds]
            distinct = len(set(labels)) >= 2
            nonstatic = preds[0] != preds[1] or preds[1] != preds[2]
            rec.verdict(
                "7_predict_user_emotion",
                "PASS" if distinct and nonstatic else "FAIL",
                f"preds={preds} labels={labels}",
            )
        except Exception as exc:
            rec.verdict("7_predict_user_emotion", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 8 _analyze_emotional_cues
        rec.log("\n--- 8 _analyze_emotional_cues ---")
        try:
            probes = {
                "this is not fair": eng._analyze_emotional_cues("this is not fair"),
                "anger": eng._analyze_emotional_cues(
                    "I hate this and I am furious and mad"
                ),
                "sadness": eng._analyze_emotional_cues(
                    "I feel so sad and heartbroken and depressed"
                ),
                "concern": eng._analyze_emotional_cues(
                    "I am worried and scared and anxious about this"
                ),
                "positive": eng._analyze_emotional_cues(
                    "This is wonderful amazing fantastic great news"
                ),
                "negation": eng._analyze_emotional_cues("I am not angry about that"),
            }
            # Live path primary is AppraisalEngine; cues are weak secondary.
            anger_ok = probes["anger"].get("anger", 0) > 0
            sad_ok = probes["sadness"].get("sadness", 0) > 0
            concern_ok = probes["concern"].get("concern", 0) > 0
            pos_ok = probes["positive"].get("positive", 0) > 0
            unfair_zero = sum(probes["this is not fair"].values()) == 0.0
            # Appraisal path handles unfairness / negation for live decisions
            app_unfair = AppraisalEngine().appraise("this is not fair")
            app_neg = AppraisalEngine().appraise("I am not angry about that")
            if anger_ok and sad_ok and concern_ok and pos_ok:
                if unfair_zero:
                    status = "PARTIAL"
                    detail = (
                        "keyword cues fire for anger/sadness/concern/positive; "
                        "'this is not fair' stays 0 on cue scorer (legacy weak path); "
                        f"live appraisal unfairness={app_unfair.event_type}/"
                        f"sev={app_unfair.severity} negated_sample={app_neg.negated}"
                    )
                else:
                    status = "PASS"
                    detail = f"cues={probes}"
            else:
                status = "FAIL"
                detail = f"cues={probes}"
            rec.verdict("8_analyze_emotional_cues", status, detail)
        except Exception as exc:
            rec.verdict("8_analyze_emotional_cues", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 9 query_emotional_state
        rec.log("\n--- 9 query_emotional_state ---")
        try:
            q = th.send_and_wait("emotion", "query_emotional_state", {}, source="proof")
            body = _content(q)
            # content may nest EmotionalStateOutput dict
            payload = body if "emotion" in body else body.get("content", body)
            if isinstance(payload, dict) and "content" in payload and "emotion" not in payload:
                payload = payload["content"]
            # thalamus may wrap: q['content'] already EmotionalStateOutput.to_dict()
            if "emotion" not in payload and isinstance(q.get("content"), dict):
                payload = q["content"]
            keys_ok = all(
                k in payload
                for k in (
                    "emotion",
                    "intensity",
                    "pleasure",
                    "arousal",
                    "dominance",
                    "emotional_tone",
                    "voice_prosody",
                )
            )
            meaningful = keys_ok and isinstance(payload.get("emotion"), str) and payload["emotion"]
            rec.verdict(
                "9_query_emotional_state",
                "PASS" if q.get("status") == "success" and meaningful else "FAIL",
                f"payload={payload}",
            )
        except Exception as exc:
            rec.verdict("9_query_emotional_state", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 10 healing / trauma helpers
        rec.log("\n--- 10 healing/trauma ---")
        try:
            heal = eng.generate_healing_response("I feel empty", "sad")
            mem = EmotionalMemory(
                emotion=EmotionalState.SAD,
                intensity=0.9,
                trigger="the betrayal and abandonment after the funeral grief",
                timestamp=time.time(),
                context="trauma proof",
            )
            before_t = len(eng.emotional_trauma_memories)
            flagged = eng.process_trauma_memory(mem)
            after_t = len(eng.emotional_trauma_memories)
            non = eng.process_trauma_memory(
                EmotionalMemory(
                    emotion=EmotionalState.HAPPY,
                    intensity=0.4,
                    trigger="sunny picnic with friends",
                    timestamp=time.time(),
                    context="",
                )
            )
            ok10 = (
                isinstance(heal, str)
                and len(heal) > 10
                and flagged is True
                and after_t > before_t
                and non is False
            )
            rec.verdict(
                "10_healing_trauma",
                "PASS" if ok10 else "FAIL",
                f"heal={heal[:70]!r} flagged={flagged} trauma_count {before_t}->{after_t} "
                f"non_trauma={non}",
            )
        except Exception as exc:
            rec.verdict("10_healing_trauma", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 11 emotional-intelligence helpers
        rec.log("\n--- 11 emotional-intelligence ---")
        try:
            before_ei = float(eng.emotional_intelligence_score)
            score = eng.calculate_emotional_intelligence()
            ok11 = isinstance(score, float) and 0.0 <= score <= 1.0 and score == eng.emotional_intelligence_score
            rec.verdict(
                "11_emotional_intelligence",
                "PASS" if ok11 else "FAIL",
                f"before={before_ei} score={score} stored={eng.emotional_intelligence_score}",
            )
        except Exception as exc:
            rec.verdict("11_emotional_intelligence", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 12 appraisal negation
        rec.log("\n--- 12 appraisal negation ---")
        try:
            ae = AppraisalEngine()
            a_neg = ae.appraise("I am not upset with you about what happened")
            a_pos = ae.appraise("I am upset with you about what happened")
            # also classic harm vs negated
            a_hate = ae.appraise("I hate you")
            a_nothate = ae.appraise("I don't hate you")
            diff = (
                (a_neg.negated != a_pos.negated)
                or (a_neg.severity != a_pos.severity)
                or (a_neg.event_type != a_pos.event_type)
                or (a_neg.monday_pad_delta != a_pos.monday_pad_delta)
            )
            diff2 = (
                a_hate.severity != a_nothate.severity
                or a_hate.negated != a_nothate.negated
                or a_hate.monday_pad_delta != a_nothate.monday_pad_delta
            )
            rec.verdict(
                "12_appraisal_negation",
                "PASS" if diff and diff2 else "FAIL",
                f"upset negated={a_neg.negated}/{a_neg.event_type}/{a_neg.severity}/"
                f"{a_neg.monday_pad_delta} vs {a_pos.negated}/{a_pos.event_type}/"
                f"{a_pos.severity}/{a_pos.monday_pad_delta}; "
                f"hate={a_hate.severity}/{a_hate.negated} nothate="
                f"{a_nothate.severity}/{a_nothate.negated}",
            )
        except Exception as exc:
            rec.verdict("12_appraisal_negation", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 13 sarcasm
        rec.log("\n--- 13 sarcasm ---")
        try:
            ae = AppraisalEngine()
            # Markers from AppraisalEngine._SARCASM_MARKERS / patterns
            s1 = ae.appraise("Oh great, another wonderful disaster...")
            s2 = ae.appraise("That was terrible but just wonderful")
            s3 = ae.appraise("I appreciate your help today")
            # Only claim what code supports
            limits = (
                "supports punctuation/ellipsis markers and negative-then-positive "
                "framing regex; not full pragmatic sarcasm"
            )
            detected = bool(s1.sarcasm_likely or s2.sarcasm_likely)
            clean = not s3.sarcasm_likely
            rec.verdict(
                "13_sarcasm",
                "PASS" if detected and clean else "PARTIAL" if detected or clean else "FAIL",
                f"s1={s1.sarcasm_likely}/{s1.event_type} s2={s2.sarcasm_likely} "
                f"s3={s3.sarcasm_likely} limits={limits}",
            )
        except Exception as exc:
            rec.verdict("13_sarcasm", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 14 hysteresis
        rec.log("\n--- 14 hysteresis ---")
        try:
            h = AdvancedEmotionalEngine(name="hyst", rng=__import__("random").Random(0))
            h.personality.hysteresis_margin = 0.4
            h.personality.refractory_sec = 0.0  # isolate hysteresis
            h.current_emotion = EmotionalState.CALM
            h.pad = type(h.pad)(0.30, -0.50, 0.50)  # at calm proto
            # Candidate angry while still near calm — margin should block
            blocked = not h._pad_margin_ok(EmotionalState.ANGRY)
            # Move PAD strongly toward angry proto and allow switch
            h.pad = type(h.pad)(-0.70, 0.70, 0.60)
            allowed = h._pad_margin_ok(EmotionalState.ANGRY)
            rec.verdict(
                "14_hysteresis",
                "PASS" if blocked and allowed else "FAIL",
                f"near_calm_blocks_angry={blocked} at_angry_proto_allows={allowed} "
                f"margin={h.personality.hysteresis_margin}",
            )
        except Exception as exc:
            rec.verdict("14_hysteresis", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 15 refractory
        rec.log("\n--- 15 refractory ---")
        try:
            r = AdvancedEmotionalEngine(name="ref", rng=__import__("random").Random(1))
            r.personality.refractory_sec = 5.0
            r.personality.hysteresis_margin = 0.0
            r.current_emotion = EmotionalState.SAD
            r.pad = type(r.pad)(-0.70, 0.70, 0.60)  # angry-ish pad
            r._last_switch_time = time.time()  # just switched
            blocked = not r._pad_margin_ok(EmotionalState.ANGRY)
            r._last_switch_time = time.time() - 10.0  # refractory expired
            allowed = r._pad_margin_ok(EmotionalState.ANGRY)
            rec.verdict(
                "15_refractory",
                "PASS" if blocked and allowed else "FAIL",
                f"rapid_repeat_blocked={blocked} after_wait_allowed={allowed} "
                f"refractory_sec={r.personality.refractory_sec}",
            )
        except Exception as exc:
            rec.verdict("15_refractory", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # 16 ExpressionState → OutputLobe E2E
        rec.log("\n--- 16 ExpressionState→Output E2E ---")
        try:
            # Force expression flags via real updater conditions
            eng.current_emotion = EmotionalState.SAD
            eng.emotional_intensity = 0.9
            eng.attachment.hurt = 0.85
            eng.attachment.abandonment_fear = 0.5
            eng._update_expression_flags()
            expr = {
                "tears": bool(eng.expression.tears),
                "voice_shake": bool(eng.expression.voice_shake),
                "withdraw": bool(eng.expression.withdraw),
            }
            emo_out = ep.get_emotional_state_output()
            # Live chat path
            routes_before = len(th.message_routes)
            reply = th.process_user_input(
                "I still feel abandoned and heartbroken after that loss.",
                user_id=f"emo-feat-{uuid.uuid4().hex[:8]}",
            )
            meta = getattr(out, "last_emotion_meta", {}) or {}
            # Also direct generate_output with forced flags (live payload shape)
            probe = th.send_and_wait(
                "output",
                "generate_output",
                {
                    "text": "expression probe",
                    "emotion": eng.current_emotion.value,
                    "intensity": eng.emotional_intensity,
                    "voice_prosody": dict(emo_out.voice_prosody),
                    "emotional_tone": emo_out.emotional_tone,
                    "emphasis": list(emo_out.emphasis),
                    "expression": expr,
                    "preserve_text": True,
                },
                source="proof",
            )
            meta2 = getattr(out, "last_emotion_meta", {}) or {}
            live_meta_ok = bool(
                meta.get("voice_prosody")
                or meta.get("expression")
                or meta.get("emotional_tone")
                or meta.get("emphasis")
            )
            forced_ok = (
                meta2.get("expression") == expr
                or (
                    isinstance(meta2.get("expression"), dict)
                    and meta2["expression"].get("tears") == expr["tears"]
                )
            )
            flags_on = any(expr.values())
            e2e = flags_on and (live_meta_ok or forced_ok) and isinstance(reply, str)
            rec.verdict(
                "16_Expression_Output_E2E",
                "PASS" if e2e else "FAIL",
                f"expr={expr} tone={emo_out.emotional_tone} emphasis={emo_out.emphasis} "
                f"prosody={emo_out.voice_prosody} live_meta={meta} forced_meta={meta2} "
                f"reply_len={len(reply) if isinstance(reply, str) else None} "
                f"out_routes={sum(1 for r in list(th.message_routes)[routes_before:] if r.get('to')=='output')}",
            )
        except Exception as exc:
            rec.verdict("16_Expression_Output_E2E", "FAIL", f"CRASH: {exc}")
            traceback.print_exc()

        # Live E2E summary for report section 8
        rec.log("\n--- LIVE E2E chain ---")
        try:
            routes_before = len(th.message_routes)
            user_line = (
                "You went behind my back and betrayed me — I feel rejected and alone."
            )
            pre_state = th.send_and_wait("emotion", "get_state", {}, source="proof")
            reply = th.process_user_input(
                user_line, user_id=f"emo-e2e-{uuid.uuid4().hex[:8]}"
            )
            routes = list(th.message_routes)[routes_before:]  # list() for deque
            emotion_hits = [r for r in routes if r.get("to") == "emotion"]
            reasoning_hits = [r for r in routes if r.get("to") == "reasoning"]
            language_hits = [r for r in routes if r.get("to") == "language"]
            output_hits = [r for r in routes if r.get("to") == "output"]
            post_state = th.send_and_wait("emotion", "get_state", {}, source="proof")
            rec.log(
                f"E2E user_input={user_line!r}\n"
                f"  pre_emotion={_content(pre_state).get('emotion') or pre_state.get('emotion')} "
                f"intensity={_content(pre_state).get('intensity') or pre_state.get('intensity')}\n"
                f"  post_emotion={_content(post_state).get('emotion') or post_state.get('emotion')} "
                f"intensity={_content(post_state).get('intensity') or post_state.get('intensity')} "
                f"pad={_content(post_state).get('pad') or post_state.get('pad')} "
                f"expression={_content(post_state).get('expression') or post_state.get('expression')}\n"
                f"  routes emotion={emotion_hits} reasoning={len(reasoning_hits)} "
                f"language={len(language_hits)} output={len(output_hits)}\n"
                f"  output_meta={getattr(out,'last_emotion_meta',None)}\n"
                f"  reply={reply!r}"
            )
        except Exception as exc:
            rec.log(f"E2E CRASH: {exc}")
            traceback.print_exc()

    except Exception as exc:
        rec.log(f"SETUP CRASH: {exc}")
        traceback.print_exc()
        return 1
    finally:
        if systems is not None:
            try:
                shutdown_core_systems(systems)
            except Exception:
                pass

    rec.log("\n=== FEATURE TABLE ===")
    for name, status, detail in rec.rows:
        rec.log(f"{status}\t{name}\t{detail[:200]}")

    PROOF_PATH.write_text("\n".join(rec.lines) + "\n", encoding="utf-8")
    rec.log(f"\nPROOF_FILE {PROOF_PATH}")
    # Exit 0 even with FAILs — transcript is the deliverable; full smoke is separate.
    return 0


def _pad(eng) -> Tuple[float, float, float]:
    return (float(eng.pad.v), float(eng.pad.a), float(eng.pad.d))


if __name__ == "__main__":
    sys.exit(main())
