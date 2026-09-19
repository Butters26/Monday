#!/usr/bin/env python3
"""Selection, satiation, mode progression, and speak-relevance helpers for AutonomousThinkingLoop."""
from __future__ import annotations

import hashlib
import json
import random
import re
import time
from typing import Any, Dict, List, Optional, Tuple

_LIGHT_TURN_RE = re.compile(
    r"\b("
    r"hey|hi|hello|yo|sup|"
    r"still with me|you there|are you (?:there|ok|okay)|"
    r"what'?s up|how are you|how'?s it going|"
    r"weather|good morning|good night|thanks|thank you"
    r")\b",
    re.I,
)

THOUGHT_MODES = (
    "replay_recall",
    "emotional_reaction",
    "interpretation",
    "cause_effect",
    "uncertainty",
    "connection",
    "self_state",
    "goal_need",
    "next_action",
    "letting_go",
    "spontaneous",
)


class AutonomousSelectionMixin:
    """Mixin: topic satiation, mode progression, resolution demotion, speak gate."""

    def _note_user_turn(self, text: str) -> None:
        self.last_user_text = text
        marker = re.search(r"(MARKER_[A-Za-z0-9_\-]+)", text)
        if marker:
            self.current_conversation_topic = marker.group(1)
        else:
            if not _LIGHT_TURN_RE.search(text) or len(text.split()) > 8:
                self.current_conversation_topic = text[:80]
        # Light check-ins: demote pending speak-worthy asides that do not overlap this turn.
        if _LIGHT_TURN_RE.search(text):
            lock = getattr(self, "lock", None)
            queue = getattr(self, "thought_queue", None)

            def _demote_queue():
                if queue is None:
                    return
                remaining = []
                for th in list(queue):
                    content = getattr(th, "content", None)
                    if content is None and isinstance(th, dict):
                        content = th.get("content")
                    topic = getattr(th, "topic_key", None)
                    if topic is None and isinstance(th, dict):
                        topic = th.get("topic_key")
                    if self._content_overlaps_turn(str(content or ""), text, str(topic or "")):
                        remaining.append(th)
                        continue
                    if hasattr(th, "speak_worthy"):
                        th.speak_worthy = False
                        try:
                            th.relevance_gate_reason = "demoted_on_light_turn"
                        except Exception:
                            pass
                    self.demote_aside_to_internal(
                        th if isinstance(th, dict) else {"topic_key": topic, "content": content}
                    )
                    # Drop from speak queue — thought already lives in recent_thoughts.
                queue[:] = remaining

            if queue is not None:
                if lock is not None:
                    with lock:
                        _demote_queue()
                else:
                    _demote_queue()
        low = text.lower()
        now = time.time()
        for key in list(getattr(self, "_think_satiation", {}).keys()):
            parts = key.split(":")
            for p in parts[1:]:
                if len(p) >= 4 and p.lower() in low:
                    self._topic_reactivated_at[key] = now
                    self._think_satiation[key] = max(0.0, self._think_satiation.get(key, 0.0) * 0.35)
                    break
        for et in (
            "betrayal", "harm", "rejection", "abandonment", "threat", "loss",
            "unfairness", "conflict", "criticism", "success", "affection", "support",
        ):
            if et in low:
                for key in list(self._think_satiation.keys()):
                    if key.startswith(f"app:{et}") or f":{et}:" in f":{key}:":
                        self._topic_reactivated_at[key] = now
                        self._think_satiation[key] = max(0.0, self._think_satiation.get(key, 0.0) * 0.25)

    @staticmethod
    def _hash_snippet(text: str, n: int = 12) -> str:
        return hashlib.sha1((text or "").encode("utf-8", errors="ignore")).hexdigest()[:n]

    def _topic_key_for_memory(self, memory: Dict[str, Any]) -> str:
        mid = memory.get("id") or memory.get("memory_id") or memory.get("uuid")
        if mid:
            return f"mem:{mid}"
        snippet = self._memory_snippet(memory, max_len=200)
        marker = re.search(r"(MARKER_[A-Za-z0-9_\-]+)", snippet)
        if marker:
            return f"mem:marker:{marker.group(1)}"
        return f"mem:h:{self._hash_snippet(snippet)}"

    def _topic_key_for_appraisal(self, appraisal: Dict[str, Any]) -> str:
        et = str(appraisal.get("event_type") or "event").strip().lower() or "event"
        snippet = str(
            appraisal.get("content")
            or appraisal.get("summary")
            or appraisal.get("trigger")
            or et
        )
        marker = re.search(r"(MARKER_[A-Za-z0-9_\-]+)", snippet)
        if marker:
            return f"app:{et}:{marker.group(1)}"
        return f"app:{et}:{self._hash_snippet(snippet)}"

    def _decayed_score(self, store, updated, key, half_life):
        raw = float(store.get(key, 0.0) or 0.0)
        if raw <= 0:
            return 0.0
        age = time.time() - float(updated.get(key, time.time()) or time.time())
        if age <= 0:
            return raw
        return raw * (0.5 ** (age / max(1.0, half_life)))

    def _think_sat(self, topic_key: str) -> float:
        return self._decayed_score(
            self._think_satiation, self._think_sat_updated, topic_key, self._THINK_SAT_DECAY_HALFLIFE
        )

    def _speak_sat(self, topic_key: str) -> float:
        return self._decayed_score(
            self._speak_satiation, self._speak_sat_updated, topic_key, self._SPEAK_SAT_DECAY_HALFLIFE
        )

    def _bump_think_satiation(self, topic_key: str, unresolved_severe: bool) -> None:
        if not topic_key:
            return
        now = time.time()
        cur = self._think_sat(topic_key)
        step = self._THINK_SAT_STEP * (0.45 if unresolved_severe else 1.0)
        if unresolved_severe:
            new = min(self._THINK_SAT_SEVERE_CAP + 0.25, cur + step)
        else:
            new = min(1.0, cur + step)
        self._think_satiation[topic_key] = new
        self._think_sat_updated[topic_key] = now
        self._topic_select_count[topic_key] = self._topic_select_count.get(topic_key, 0) + 1

    def _bump_speak_satiation(self, topic_key: str) -> None:
        if not topic_key:
            return
        cur = self._speak_sat(topic_key)
        self._speak_satiation[topic_key] = min(1.0, cur + self._SPEAK_SAT_STEP)
        self._speak_sat_updated[topic_key] = time.time()

    def demote_aside_to_internal(self, aside: Any) -> None:
        topic_key = ""
        if isinstance(aside, dict):
            topic_key = str(aside.get("topic_key") or "")
        if topic_key:
            cur = self._speak_sat(topic_key)
            self._speak_satiation[topic_key] = min(1.0, max(cur, 0.35))
            self._speak_sat_updated[topic_key] = time.time()

    def _update_resolution_tracking(self, emotional_state: Dict[str, Any]) -> None:
        unresolved = emotional_state.get("unresolved_appraisals") or []
        now = time.time()
        live_keys = set()
        for u in unresolved:
            if not isinstance(u, dict):
                continue
            key = self._topic_key_for_appraisal(u)
            live_keys.add(key)
            try:
                sev = float(u.get("severity", 0.0) or 0.0)
            except (TypeError, ValueError):
                sev = 0.0
            prev = self._topic_last_severity.get(key)
            if prev is not None and sev < prev - 0.08:
                self._think_satiation[key] = max(self._think_sat(key), 0.75)
                self._think_sat_updated[key] = now
            self._topic_last_severity[key] = sev
            self._topic_resolved_at.pop(key, None)
        for key in list(self._topic_last_severity.keys()):
            if key.startswith("app:") and key not in live_keys and key not in self._topic_resolved_at:
                self._topic_resolved_at[key] = now
                self._think_satiation[key] = max(self._think_sat(key), 0.85)
                self._think_sat_updated[key] = now

    def _resolution_factor(self, topic_key: str, appraisal: Optional[Dict[str, Any]]) -> float:
        if topic_key in self._topic_resolved_at:
            age = time.time() - self._topic_resolved_at[topic_key]
            if age < 600:
                return self._RESOLUTION_DEMOTE
            return min(0.4, self._RESOLUTION_DEMOTE + age / 5000.0)
        if appraisal is not None:
            try:
                sev = float(appraisal.get("severity", 0.0) or 0.0)
            except (TypeError, ValueError):
                sev = 0.0
            prev = self._topic_last_severity.get(topic_key, sev)
            if prev > 0 and sev < prev * 0.7:
                return 0.25
            if sev < 0.35:
                return 0.35
        return 1.0

    def _association_boost(self, topic_key: str, event_type: Any, snippet: Optional[str]) -> float:
        boost = 1.0
        focus = (self.current_conversation_topic or "").lower()
        last = (self.last_user_text or "").lower()
        hay = f"{topic_key} {event_type or ''} {snippet or ''}".lower()
        if focus and focus in hay:
            boost *= 1.25
        if last and not _LIGHT_TURN_RE.search(last):
            tokens = [
                t for t in re.findall(r"[a-z0-9_]{4,}", last)
                if t not in {"that", "this", "with", "have", "about"}
            ]
            hits = sum(1 for t in tokens[:12] if t in hay)
            if hits:
                boost *= 1.0 + min(0.35, 0.08 * hits)
        if self.current_focus and str(self.current_focus).lower() in hay:
            boost *= 1.15
        return boost

    def _select_thought_candidate(self, emotional_state, memories, values):
        unresolved = [
            u for u in (emotional_state.get("unresolved_appraisals") or [])
            if isinstance(u, dict)
        ]
        try:
            intensity = float(emotional_state.get("intensity", 0.5) or 0.5)
        except (TypeError, ValueError):
            intensity = 0.5
        emotion = str(emotional_state.get("emotion") or "neutral")
        primary = self._primary_unresolved(emotional_state)
        usable = self._prefer_grounding_memories(memories, primary)
        candidates = []

        for u in unresolved:
            key = self._topic_key_for_appraisal(u)
            try:
                sev = float(u.get("severity", 0.0) or 0.0)
            except (TypeError, ValueError):
                sev = 0.0
            weight = (0.55 + 0.45 * sev) * (0.55 + 0.45 * intensity)
            weight *= self._resolution_factor(key, u)
            sat = self._think_sat(key)
            severe = sev >= 0.65 and key not in self._topic_resolved_at
            weight *= max(0.05, 1.0 - sat * (0.55 if severe else 1.0))
            if key in self._topic_reactivated_at and (time.time() - self._topic_reactivated_at[key]) < 120:
                weight *= 1.35
            weight *= self._association_boost(key, u.get("event_type"), None)
            sel_n = self._topic_select_count.get(key, 0)
            if sel_n >= 3:
                weight *= max(0.08, 0.7 ** (sel_n - 2))
            candidates.append({
                "kind": "appraisal", "topic_key": key, "weight": weight,
                "appraisal": u, "memory": None, "severe": severe,
            })

        for m in usable[:8]:
            key = self._topic_key_for_memory(m)
            snippet = self._memory_snippet(m)
            try:
                importance = float(m.get("importance") or m.get("salience") or 5.0)
            except (TypeError, ValueError):
                importance = 5.0
            weight = 0.35 + 0.06 * min(10.0, importance)
            matched_app = None
            if primary:
                et = str(primary.get("event_type") or "").lower()
                if et and et in snippet.lower():
                    weight += 0.25
                    matched_app = primary
                elif any(w in snippet.lower() for w in ("trust", "hurt", "broke", "behind", "shared")):
                    weight += 0.12
                    matched_app = primary
            weight *= (0.6 + 0.4 * intensity) if matched_app else (0.75 + 0.15 * intensity)
            if matched_app:
                weight *= self._resolution_factor(self._topic_key_for_appraisal(matched_app), matched_app)
            else:
                weight *= self._resolution_factor(key, None)
            sat = self._think_sat(key)
            severe = bool(matched_app) and float(matched_app.get("severity", 0) or 0) >= 0.65
            weight *= max(0.05, 1.0 - sat * (0.55 if severe else 1.0))
            ts = m.get("timestamp") or m.get("created_at") or m.get("time")
            try:
                age = max(0.0, time.time() - float(ts))
                weight *= max(0.4, 1.0 - min(age, 3600) / 5000.0)
            except (TypeError, ValueError):
                pass
            weight *= self._association_boost(key, None, snippet)
            sel_n = self._topic_select_count.get(key, 0)
            if sel_n >= 3 and key not in self._topic_reactivated_at:
                weight *= max(0.08, 0.7 ** (sel_n - 2))
            elif sel_n >= 3:
                re_age = time.time() - self._topic_reactivated_at.get(key, 0)
                if re_age > 180:
                    weight *= max(0.1, 0.75 ** (sel_n - 2))
            candidates.append({
                "kind": "memory", "topic_key": key, "weight": weight,
                "appraisal": matched_app, "memory": m, "severe": severe,
            })

        self_key = "self:state"
        self_w = 0.22 + 0.15 * abs(intensity - 0.5)
        if emotion not in ("neutral", "calm"):
            self_w += 0.12
        if candidates and max(c["weight"] for c in candidates) < 0.35:
            self_w += 0.18
        # Soft boost once other topics have been chewed — then apply satiation on the total.
        if any(self._topic_select_count.get(c["topic_key"], 0) >= 2 for c in candidates):
            self_w += 0.12
        self_w *= max(0.08, 1.0 - self._think_sat(self_key) * 0.9)
        sel_self = self._topic_select_count.get(self_key, 0)
        if sel_self >= 3:
            self_w *= max(0.06, 0.6 ** (sel_self - 2))
        candidates.append({
            "kind": "self_state", "topic_key": self_key, "weight": self_w,
            "appraisal": None, "memory": None, "severe": False,
        })

        if values:
            v = values[0]
            vname = str(v.get("name") or "value")
            gkey = f"goal:{vname}"
            gw = 0.18 * max(0.15, 1.0 - self._think_sat(gkey))
            candidates.append({
                "kind": "goal", "topic_key": gkey, "weight": gw,
                "appraisal": None, "memory": None, "value": v, "severe": False,
            })

        spont_key = "spontaneous"
        sw = 0.12
        if not unresolved and intensity < 0.45:
            sw = 0.45
        elif candidates and max(c["weight"] for c in candidates) < 0.28:
            sw = 0.40
        # When self-state is satiated, quiet spontaneous should win the idle stretch.
        if self._think_sat("self:state") >= 0.55 and not unresolved:
            sw = max(sw, 0.58)
        sw *= max(0.2, 1.0 - self._think_sat(spont_key) * 0.7)
        candidates.append({
            "kind": "spontaneous", "topic_key": spont_key, "weight": sw,
            "appraisal": None, "memory": None, "severe": False,
        })

        if not candidates:
            return None
        candidates.sort(key=lambda c: c["weight"], reverse=True)
        best_w = candidates[0]["weight"]
        tied = [c for c in candidates if c["weight"] >= best_w * 0.92]
        return random.choice(tied) if len(tied) > 1 else candidates[0]

    def _select_mode_for_candidate(self, candidate, emotional_state):
        kind = candidate.get("kind")
        topic_key = candidate.get("topic_key") or ""
        recent = list(self._topic_last_modes.get(topic_key, []))
        try:
            intensity = float(emotional_state.get("intensity", 0.5) or 0.5)
        except (TypeError, ValueError):
            intensity = 0.5
        unresolved = emotional_state.get("unresolved_appraisals") or []
        sel_n = self._topic_select_count.get(topic_key, 0)
        if kind == "spontaneous":
            return "spontaneous"
        if kind == "self_state":
            return "self_state"
        if kind == "goal":
            return "goal_need"
        ladder = [
            "replay_recall", "emotional_reaction", "interpretation", "cause_effect",
            "uncertainty", "connection", "self_state", "goal_need", "next_action", "letting_go",
        ]
        if topic_key in self._topic_resolved_at or self._resolution_factor(
            topic_key, candidate.get("appraisal")
        ) < 0.4:
            preferred = ["letting_go", "self_state", "next_action", "connection"]
        elif sel_n == 0:
            preferred = ["replay_recall", "emotional_reaction"]
        elif intensity < 0.4 and not unresolved:
            preferred = ["letting_go", "self_state", "spontaneous", "next_action"]
        else:
            preferred = [m for m in ladder if m not in recent[-3:]] or list(ladder)
        for m in preferred:
            if m not in recent[-2:]:
                return m
        last = recent[-1] if recent else None
        for m in ladder:
            if m != last:
                return m
        return preferred[0] if preferred else "self_state"

    def _find_connection_snippet(self, memories, current, appraisal):
        cur_key = self._topic_key_for_memory(current) if current else ""
        for m in memories or []:
            if not isinstance(m, dict):
                continue
            if current is not None and self._topic_key_for_memory(m) == cur_key:
                continue
            sn = self._memory_snippet(m, max_len=80)
            if not sn or self._is_boilerplate_memory(sn):
                continue
            return sn
        if appraisal and appraisal.get("event_type"):
            return f"earlier {appraisal.get('event_type')} residue"
        return ""

    def _generate_mode_content(self, mode, candidate, emotional_state, memories, values):
        emotion = str(emotional_state.get("emotion") or "neutral")
        try:
            intensity = float(emotional_state.get("intensity", 0.5) or 0.5)
        except (TypeError, ValueError):
            intensity = 0.5
        mem = candidate.get("memory") if isinstance(candidate.get("memory"), dict) else None
        appraisal = candidate.get("appraisal") if isinstance(candidate.get("appraisal"), dict) else None
        snippet = self._memory_snippet(mem) if mem else ""
        event = str((appraisal or {}).get("event_type") or "").strip()
        if not snippet and event:
            snippet = f"that {event}"

        thought_type = {
            "replay_recall": "memory",
            "emotional_reaction": "feeling",
            "interpretation": "reflection",
            "cause_effect": "reflection",
            "uncertainty": "question",
            "connection": "memory",
            "self_state": "observation",
            "goal_need": "reflection",
            "next_action": "reflection",
            "letting_go": "feeling",
            "spontaneous": "observation",
        }.get(mode, "reflection")

        if mode == "spontaneous":
            return (
                f"A quiet beat — nothing strongly demands attention. I am {emotion} at {intensity:.2f}.",
                "spontaneous",
                thought_type,
            )
        if mode == "self_state" and candidate.get("kind") in ("self_state", "spontaneous"):
            return (
                f"I notice I am {emotion} even in the quiet — intensity {intensity:.2f}. "
                f"Tracking my own weather, not guessing someone else's.",
                "self_state",
                thought_type,
            )
        if mode == "goal_need" and candidate.get("kind") == "goal":
            v = candidate.get("value") or {}
            vname = v.get("name", "what matters")
            return (
                f"Am I living {vname} while I feel {emotion}, or just reacting?",
                f"goal_{vname}",
                thought_type,
            )

        s = snippet or (f"that {event}" if event else "what just happened")
        quoted = f'"{s}"' if mem and s and not s.startswith("that ") else s
        if mode == "replay_recall":
            content = f"I keep replaying {quoted}."
        elif mode == "emotional_reaction":
            content = f"Sitting with {quoted} — I feel {emotion} at {intensity:.2f}."
        elif mode == "interpretation":
            why = f" as {event}" if event else ""
            content = (
                f"What I make of {quoted}{why}: it still shapes how I read things "
                f"while I am {emotion}."
            )
        elif mode == "cause_effect":
            content = (
                f"If {quoted} landed like this, no wonder I am {emotion} — "
                f"cause and effect, not mirroring."
            )
        elif mode == "uncertainty":
            content = f"I am not sure what {quoted} still needs from me. What would actually help?"
        elif mode == "connection":
            other = self._find_connection_snippet(memories, mem, appraisal)
            if other:
                content = f'{quoted} links in my mind to "{other}" — same thread, different angle.'
            else:
                content = f"{quoted} connects to how I am holding myself right now ({emotion})."
        elif mode == "self_state":
            content = f"Underneath the content, my own state is {emotion} @ {intensity:.2f}."
        elif mode == "goal_need":
            need = "clarity" if emotion in ("anxious", "worried", "frustrated") else "steadiness"
            content = f"What I need around {quoted} is {need}, not another loop of the same words."
        elif mode == "next_action":
            content = (
                f"Possible next step: name what {quoted} changed for me, "
                f"then let the quiet be quiet."
            )
        elif mode == "letting_go":
            content = (
                f"I can remember {quoted} without letting it run every cycle. "
                f"Softening my grip while still {emotion}."
            )
        else:
            content = f"Noticing {quoted} while I am {emotion}."

        if event and candidate.get("kind") == "appraisal":
            trigger = f"appraisal_{event}_{mode}"
        elif mem:
            trigger = f"memory_{mode}"
        else:
            trigger = f"grounded_{mode}"
        return content, trigger, thought_type

    def _topic_still_urgent(self, topic_key, emotional_state, candidate=None):
        try:
            intensity = float(emotional_state.get("intensity", 0.5) or 0.5)
        except (TypeError, ValueError):
            intensity = 0.5
        if topic_key in self._topic_resolved_at:
            return False
        sev = 0.0
        appraisal = (candidate or {}).get("appraisal") if candidate else None
        if isinstance(appraisal, dict):
            try:
                sev = float(appraisal.get("severity", 0.0) or 0.0)
            except (TypeError, ValueError):
                sev = 0.0
        else:
            for u in (emotional_state.get("unresolved_appraisals") or []):
                if not isinstance(u, dict):
                    continue
                if self._topic_key_for_appraisal(u) == topic_key or (
                    topic_key.startswith("app:") and str(u.get("event_type") or "") in topic_key
                ):
                    try:
                        sev = float(u.get("severity", 0.0) or 0.0)
                    except (TypeError, ValueError):
                        sev = 0.0
                    break
                # memory topics tied to betrayal content: use max unresolved sev lightly
                if topic_key.startswith("mem:") and u.get("event_type"):
                    try:
                        sev = max(sev, float(u.get("severity", 0.0) or 0.0) * 0.85)
                    except (TypeError, ValueError):
                        pass
        if sev >= 0.7 and intensity >= 0.55:
            return True
        if sev >= 0.85 and intensity >= 0.45:
            return True
        if intensity >= 0.75 and sev >= 0.5:
            return True
        return False

    def _content_overlaps_turn(self, content, user_text, topic_key=""):
        if not user_text or not str(user_text).strip():
            return False
        low_u = user_text.lower()
        low_c = (content or "").lower()
        for m in re.findall(r"(marker_[a-z0-9_\-]+)", low_c, flags=re.I):
            if m.lower() in low_u:
                return True
        u_toks = set(re.findall(r"[a-z0-9_]{4,}", low_u))
        c_toks = set(re.findall(r"[a-z0-9_]{4,}", low_c))
        stop = {
            "that", "this", "with", "have", "about", "what", "when", "from", "they",
            "them", "were", "been", "into", "your", "their", "would", "could", "should",
            "still", "while", "feeling", "think", "thought", "monday", "matthew",
        }
        if (u_toks - stop) & (c_toks - stop):
            return True
        if topic_key and any(p for p in topic_key.split(":") if len(p) > 5 and p.lower() in low_u):
            return True
        return False

    def aside_passes_relevance_gate(self, aside, user_text=None, emotional_state=None):
        if aside is None:
            return False, "no_aside"
        if hasattr(aside, "__dataclass_fields__"):
            from dataclasses import asdict
            data = asdict(aside)
        elif isinstance(aside, dict):
            data = aside
        else:
            return False, "bad_aside_type"

        content = str(data.get("content") or "")
        topic_key = str(data.get("topic_key") or "")
        user_text = self.last_user_text if user_text is None else user_text
        emotional_state = emotional_state or self._get_emotional_state()

        if topic_key:
            if self._speak_sat(topic_key) >= 0.45:
                reactivated = topic_key in self._topic_reactivated_at and (
                    time.time() - self._topic_reactivated_at[topic_key]
                ) < 90
                if not reactivated:
                    return False, "speak_satiation_cooldown"
            last_speak = self._speak_sat_updated.get(topic_key)
            if last_speak and (time.time() - last_speak) < self._SPEAK_COOLDOWN_SEC:
                reactivated = topic_key in self._topic_reactivated_at and (
                    time.time() - self._topic_reactivated_at[topic_key]
                ) < 90
                if not reactivated:
                    return False, "speak_recently_surfaced"

        urgent = self._topic_still_urgent(topic_key, emotional_state, None)
        light = bool(user_text and _LIGHT_TURN_RE.search(user_text))
        overlaps = self._content_overlaps_turn(content, user_text or "", topic_key)
        topic_overlap = False
        if self.current_conversation_topic and not light:
            topic_overlap = self._content_overlaps_turn(
                content, self.current_conversation_topic, topic_key
            )

        if light and not overlaps:
            try:
                intensity = float(emotional_state.get("intensity", 0.5) or 0.5)
            except (TypeError, ValueError):
                intensity = 0.5
            if urgent and intensity >= 0.55:
                return True, "light_turn_but_still_urgent"
            return False, "light_turn_unrelated_not_urgent"

        if user_text and not overlaps and not topic_overlap:
            if not urgent:
                return False, "unrelated_to_turn_not_urgent"
            if self._topic_select_count.get(topic_key, 0) >= 4 and not (
                topic_key in self._topic_reactivated_at
                and time.time() - self._topic_reactivated_at[topic_key] < 120
            ):
                return False, "unrelated_turn_topic_overplayed"
            return True, "unrelated_turn_but_urgent"

        if overlaps or topic_overlap:
            return True, "overlaps_current_turn"

        if not user_text:
            if urgent:
                return True, "no_turn_but_urgent"
            try:
                intensity = float(emotional_state.get("intensity", 0.5) or 0.5)
            except (TypeError, ValueError):
                intensity = 0.5
            if intensity >= 0.7:
                return True, "no_turn_high_intensity"
            return False, "no_turn_not_urgent_keep_internal"

        return True, "default_allow"

    def _evaluate_speak_worthy(self, thought_type, mode, topic_key, content,
                               emotional_state, candidate, user_text):
        try:
            intensity = float(emotional_state.get("intensity", 0.5) or 0.5)
        except (TypeError, ValueError):
            intensity = 0.5
        unresolved = emotional_state.get("unresolved_appraisals") or []
        max_sev = 0.0
        if unresolved:
            try:
                max_sev = max(float(u.get("severity", 0.0) or 0.0) for u in unresolved)
            except Exception:
                max_sev = 0.55
        eligible = False
        if unresolved and (intensity >= 0.55 or max_sev >= 0.6) and candidate.get("kind") in (
            "appraisal", "memory"
        ):
            eligible = True
        elif intensity > 0.72 and thought_type in ("feeling", "reflection", "memory"):
            eligible = True
        elif thought_type == "question" and intensity > 0.65:
            eligible = True
        if mode == "spontaneous" and intensity < 0.7:
            eligible = False
        if self._speak_sat(topic_key) >= 0.5:
            eligible = False
        if not eligible:
            return False, "not_eligible_intensity_or_type"
        aside = {
            "content": content,
            "topic_key": topic_key,
            "source_appraisal": (candidate.get("appraisal") or {}).get("event_type")
            if isinstance(candidate.get("appraisal"), dict) else None,
            "intensity": intensity,
        }
        return self.aside_passes_relevance_gate(
            aside, user_text=user_text, emotional_state=emotional_state
        )

    def _write_trace(self, trace):
        path = getattr(self, "trace_log_path", None)
        if not path:
            return
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(json.dumps(trace, ensure_ascii=False) + "\n")
        except Exception:
            pass
