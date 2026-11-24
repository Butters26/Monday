"""Attention: what she is focused on right now.

Many things compete for her at once: what her senses bring in, her current
purpose, what her other lobes flag. Attention weighs them, the strongest wins
and becomes her focus, and scores fade when nothing refreshes them so focus
moves on.

How much something pulls at her comes from what her other lobes make of it,
never from matching words in it:
- bottom-up: how strong the sense itself is (Sensory Integration), how new it
  is (Novelty), whether it is a question or carries feeling (Language's
  reading), and how strongly she feels about it (Emotion);
- top-down: her current purpose (Executive Control), and what Meta-Cognition
  flags.

The winner is amplified: Attention turns up the Thalamus's volume for the
lobes that carry her focus. The Thalamus only applies it.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional


def _trace(kind: str, **data: Any) -> None:
    try:
        from trace_monitor import trace_event
        trace_event(kind, **data)
    except Exception:
        pass


class AttentionLobe:
    """Rank and decay competing signals; expose focus via process_message."""

    def __init__(
        self,
        thalamus: Any = None,
        decay_rate: float = 0.20,
        min_salience: float = 0.05,
    ) -> None:
        self.thalamus = thalamus
        self.current_focus: Optional[str] = None
        self.salience_map: Dict[str, float] = {}
        self.signal_meta: Dict[str, Dict[str, Any]] = {}
        self.decay_rate = float(decay_rate)
        self.min_salience = float(min_salience)
        self._last_decay_at: float = time.time()
        self._evaluate_count: int = 0

    # --- internals ---------------------------------------------------------

    @staticmethod
    def _signal_id(signal: Any, index: int = 0) -> str:
        if isinstance(signal, dict):
            for key in ("id", "signal_id", "key", "name"):
                raw = signal.get(key)
                if isinstance(raw, str) and raw.strip():
                    return raw.strip()
            text = signal.get("text") or signal.get("content") or signal.get("focus")
            source = signal.get("source") or signal.get("modality") or "signal"
            if isinstance(text, str) and text.strip():
                snippet = " ".join(text.strip().split())[:48]
                return f"{source}:{snippet}"
            return f"{source}:{index}"
        if isinstance(signal, str) and signal.strip():
            return f"raw:{signal.strip()[:48]}"
        return f"anon:{index}"

    @staticmethod
    def _normalize_signal(signal: Any, index: int = 0) -> Dict[str, Any]:
        if isinstance(signal, dict):
            text = (
                signal.get("text")
                or signal.get("content")
                or signal.get("focus")
                or ""
            )
            if not isinstance(text, str):
                text = str(text) if text is not None else ""
            try:
                novelty_score = float(signal.get("novelty_score") or 0.0)
            except (TypeError, ValueError):
                novelty_score = 0.0
            # Priority: explicit priority/base_priority win; else Meta-style urgency.
            if "priority" in signal or "base_priority" in signal:
                try:
                    raw_pri = signal.get("priority")
                    if raw_pri is None:
                        raw_pri = signal.get("base_priority")
                    priority = float(raw_pri if raw_pri is not None else 0.0)
                except (TypeError, ValueError):
                    priority = 0.0
            elif "urgency" in signal:
                try:
                    priority = float(signal.get("urgency") or 0.0)
                except (TypeError, ValueError):
                    priority = 0.0
            else:
                priority = 0.0
            norm: Dict[str, Any] = {
                "id": AttentionLobe._signal_id(signal, index),
                "text": text,
                "source": str(signal.get("source") or "unknown"),
                "modality": str(signal.get("modality") or "text"),
                "priority": priority,
                "novelty_flags": list(signal.get("novelty_flags") or []),
                "novelty_score": novelty_score,
                "emotions": list(signal.get("emotions") or []),
                "entities": list(signal.get("entities") or []),
                "concepts": list(signal.get("concepts") or signal.get("words") or []),
                # What the other lobes made of it (filled in as they report):
                "asks": bool(signal.get("asks")),        # Language read it as a question
                "feeling": bool(signal.get("feeling")),  # Language found feeling in it
                "felt": AttentionLobe._unit(signal.get("felt")),  # how strongly she feels about it (Emotion)
                "raw": signal,
            }
            return norm
        text = str(signal) if signal is not None else ""
        return {
            "id": AttentionLobe._signal_id(signal, index),
            "text": text,
            "source": "raw",
            "modality": "text",
            "priority": 0.0,
            "novelty_flags": [],
            "novelty_score": 0.0,
            "emotions": [],
            "entities": [],
            "concepts": [],
            "raw": signal,
        }

    @staticmethod
    def _unit(value: Any) -> float:
        try:
            return max(0.0, min(1.0, float(value or 0.0)))
        except (TypeError, ValueError):
            return 0.0

    def _compute_salience(self, signal: Dict[str, Any]) -> float:
        """How much a signal pulls at her (0.0–1.5), from what her lobes report about it."""
        text = (signal.get("text") or "").strip()
        score = 0.15  # baseline so empty-ish signals still exist briefly

        # Caller-supplied priority (0–1); urgency is Meta-style alias when
        # priority is absent (normalize usually folds it in already).
        try:
            raw_pri = signal.get("priority")
            if raw_pri is None:
                raw_pri = signal.get("urgency")
            score += min(1.0, max(0.0, float(raw_pri or 0.0))) * 0.45
        except (TypeError, ValueError):
            pass

        # Source priors: live user input outranks ambient/system.
        # Include current injectors (executive / meta / novelty / SI) so steers
        # and soft nudges are scored honestly — not invisible unknowns.
        source = str(signal.get("source") or "").lower()
        if source in {"user", "user_input", "chat"}:
            score += 0.35
        elif source in {"perception", "sensory", "sensory_integration"}:
            score += 0.20
        elif source in {"executive_control", "executive"}:
            score += 0.30
        elif source in {"novelty"}:
            score += 0.15
        elif source in {"meta_cognition", "meta"}:
            score += 0.10
        elif source in {"emotion", "inner", "autonomous"}:
            score += 0.15
        elif source in {"ambient", "background"}:
            score += 0.02

        modality = str(signal.get("modality") or "text").lower()
        if modality in {"audio", "vision", "visual"}:
            score += 0.12

        novelty = signal.get("novelty_flags") or []
        if novelty:
            score += min(0.40, 0.12 * len(novelty))

        # Consolidated Novelty-lobe score (0–1) — real boost, not theater.
        try:
            nov_score = float(signal.get("novelty_score") or 0.0)
        except (TypeError, ValueError):
            nov_score = 0.0
        if nov_score > 0.0:
            score += min(0.45, 0.45 * max(0.0, min(1.0, nov_score)))

        emotions = signal.get("emotions") or []
        if emotions:
            score += min(0.30, 0.10 * len(emotions))

        entities = signal.get("entities") or []
        if entities:
            score += min(0.20, 0.05 * len(entities))

        # What it means to her, as her other lobes report it (no word matching):
        # how strongly she feels about it, whether it carries feeling, whether
        # it asks something of her.
        score += 0.35 * self._unit(signal.get("felt"))
        if signal.get("feeling"):
            score += 0.20
        if signal.get("asks"):
            score += 0.15

        # Mild length signal — capped so length alone cannot dominate.
        if text:
            score += min(0.15, len(text) / 400.0)

        return round(min(1.5, max(0.0, score)), 4)

    # --- public API --------------------------------------------------------

    def decay(self, force: bool = False) -> Dict[str, Any]:
        """Multiply stored scores by (1 - decay_rate); prune below min_salience.

        Rapid back-to-back calls (<25ms) without force are no-ops so a
        double-attend glitch cannot burn salience twice in one tick.
        """
        now = time.time()
        if (
            not force
            and self.salience_map
            and (now - self._last_decay_at) < 0.025
        ):
            return {
                "decay_rate": self.decay_rate,
                "factor": 1.0,
                "remaining": len(self.salience_map),
                "dropped": [],
                "skipped": True,
            }
        factor = max(0.0, 1.0 - self.decay_rate)
        dropped: List[str] = []
        for sid in list(self.salience_map.keys()):
            self.salience_map[sid] = round(self.salience_map[sid] * factor, 4)
            if self.salience_map[sid] < self.min_salience:
                dropped.append(sid)
                self.salience_map.pop(sid, None)
                self.signal_meta.pop(sid, None)
                if self.current_focus == sid:
                    self.current_focus = None
        self._last_decay_at = now
        return {
            "decay_rate": self.decay_rate,
            "factor": factor,
            "remaining": len(self.salience_map),
            "dropped": dropped,
        }

    def update_salience(self, input_signals: Any) -> List[Dict[str, Any]]:
        """Score signals and merge into the salience map. Returns ranked entries."""
        if input_signals is None:
            signals: List[Any] = []
        elif isinstance(input_signals, (list, tuple)):
            signals = list(input_signals)
        else:
            signals = [input_signals]

        for index, raw in enumerate(signals):
            norm = self._normalize_signal(raw, index)
            sid = norm["id"]
            fresh = self._compute_salience(norm)
            # Keep a little of prior score so focus has continuity, then take max.
            prior = float(self.salience_map.get(sid, 0.0) or 0.0)
            self.salience_map[sid] = round(max(fresh, prior * 0.5 + fresh * 0.5), 4)
            self.signal_meta[sid] = norm
        return self.rank_signals()

    def remove_signals(
        self,
        ids: Any = None,
        prefix: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Drop signals by exact id and/or id prefix. Clears focus if removed."""
        targets: List[str] = []
        if ids is None:
            id_list: List[Any] = []
        elif isinstance(ids, (list, tuple, set)):
            id_list = list(ids)
        else:
            id_list = [ids]
        for raw in id_list:
            if isinstance(raw, str) and raw.strip():
                targets.append(raw.strip())
        if isinstance(prefix, str) and prefix:
            for sid in list(self.salience_map.keys()):
                if sid.startswith(prefix):
                    targets.append(sid)
        # Preserve order, unique.
        seen = set()
        ordered: List[str] = []
        for sid in targets:
            if sid not in seen:
                seen.add(sid)
                ordered.append(sid)
        removed: List[str] = []
        for sid in ordered:
            if sid in self.salience_map or sid in self.signal_meta:
                self.salience_map.pop(sid, None)
                self.signal_meta.pop(sid, None)
                if self.current_focus == sid:
                    self.current_focus = None
                removed.append(sid)
        # Keep focus honest: if we cleared it (or it is gone), pick next-best.
        if self.current_focus is None or self.current_focus not in self.salience_map:
            self.select_focus()
        return {"removed": removed, "remaining": len(self.salience_map)}

    def replace_signals(self, input_signals: Any) -> List[Dict[str, Any]]:
        """Overwrite salience/meta for each signal id (no prior blend)."""
        if input_signals is None:
            signals: List[Any] = []
        elif isinstance(input_signals, (list, tuple)):
            signals = list(input_signals)
        else:
            signals = [input_signals]

        for index, raw in enumerate(signals):
            norm = self._normalize_signal(raw, index)
            sid = norm["id"]
            fresh = self._compute_salience(norm)
            self.salience_map[sid] = fresh
            self.signal_meta[sid] = norm
        # Ranking may have changed; keep current_focus aligned with top score.
        self.select_focus()
        return self.rank_signals()

    def rank_signals(self) -> List[Dict[str, Any]]:
        """Return salience entries sorted high → low."""
        ranked: List[Dict[str, Any]] = []
        for sid, score in sorted(
            self.salience_map.items(), key=lambda item: item[1], reverse=True
        ):
            meta = self.signal_meta.get(sid) or {"id": sid, "text": sid}
            ranked.append(
                {
                    "id": sid,
                    "score": score,
                    "text": meta.get("text", ""),
                    "source": meta.get("source", "unknown"),
                    "modality": meta.get("modality", "text"),
                    "signal": meta,
                }
            )
        return ranked

    def select_focus(self) -> Optional[str]:
        """Select highest-salience signal id as current focus."""
        ranked = self.rank_signals()
        if not ranked:
            self.current_focus = None
            return None
        self.current_focus = ranked[0]["id"]
        return self.current_focus

    def evaluate(self, input_signals: Any) -> Dict[str, Any]:
        """Decay → update → stale-absent decay → select.

        Signals present in this pass are refreshed; competitors absent from
        the batch take an extra decay tick so leftover novelty/entity/meta
        entries cannot steal focus across turns.
        """
        decay_info = self.decay(force=True)
        if input_signals is None:
            batch: List[Any] = []
        elif isinstance(input_signals, (list, tuple)):
            batch = list(input_signals)
        else:
            batch = [input_signals]
        incoming_ids = {
            self._normalize_signal(raw, index)["id"] for index, raw in enumerate(batch)
        }
        ranked = self.update_salience(batch)
        stale_dropped: List[str] = []
        if self.salience_map and incoming_ids:
            factor = max(0.0, 1.0 - self.decay_rate)
            for sid in list(self.salience_map.keys()):
                if sid in incoming_ids:
                    continue
                self.salience_map[sid] = round(self.salience_map[sid] * factor, 4)
                if self.salience_map[sid] < self.min_salience:
                    stale_dropped.append(sid)
                    self.salience_map.pop(sid, None)
                    self.signal_meta.pop(sid, None)
                    if self.current_focus == sid:
                        self.current_focus = None
            if stale_dropped:
                decay_info = dict(decay_info)
                decay_info["stale_dropped"] = stale_dropped
                decay_info["remaining"] = len(self.salience_map)
            ranked = self.rank_signals()
        focus_id = self.select_focus()
        focus_entry = next((r for r in ranked if r.get("id") == focus_id), None)
        if focus_entry is None:
            focus_entry = ranked[0] if ranked else None
        self._evaluate_count += 1
        return {
            "focus": focus_id,
            "focus_text": (focus_entry or {}).get("text"),
            "focus_score": (focus_entry or {}).get("score"),
            "focus_source": (focus_entry or {}).get("source"),
            "ranked": ranked,
            "salience_map": dict(self.salience_map),
            "decay": decay_info,
            "evaluate_count": self._evaluate_count,
        }

    def route_focus(self) -> Dict[str, Any]:
        """Route current focus to reasoning via thalamus when both exist."""
        if not self.current_focus:
            return {"routed": False, "reason": "no_focus"}
        meta = self.signal_meta.get(self.current_focus) or {}
        payload = {
            "focus": self.current_focus,
            "focus_text": meta.get("text"),
            "score": self.salience_map.get(self.current_focus),
            "source": meta.get("source"),
            "modality": meta.get("modality"),
        }
        if not self.thalamus:
            return {"routed": False, "reason": "no_thalamus", "payload": payload}
        tell = getattr(self.thalamus, "tell", None)
        if not callable(tell):
            return {"routed": False, "reason": "thalamus_has_no_tell", "payload": payload}
        # Told, not asked: Attention doesn't wait on Reasoning to carry on.
        response = tell("reasoning", "attention_focus", payload, source="attention")
        return {
            "routed": response.get("status") == "delivered",
            "response": response,
            "payload": payload,
        }

    # --- on the team ---------------------------------------------------------

    # Which lobes' messages carry each kind of signal she can focus on.
    _CARRIED_BY = {
        "user": ("perception", "sensory_integration"),
        "user_input": ("perception", "sensory_integration"),
        "chat": ("perception", "sensory_integration"),
        "perception": ("perception", "sensory_integration"),
        "sensory": ("perception", "sensory_integration"),
        "sensory_integration": ("perception", "sensory_integration"),
        "executive": ("executive_control",),
        "executive_control": ("executive_control",),
        "novelty": ("novelty",),
        "meta": ("meta_cognition",),
        "meta_cognition": ("meta_cognition",),
        "emotion": ("emotion",),
        "autonomous": ("autonomous",),
        "inner": ("autonomous",),
    }
    _WINNER_VOLUME = 2.0

    def on_joined(self, name: str) -> None:
        from team import listen
        listen(self.thalamus, name, "moment")

    def _take_in(self, content: Dict[str, Any]) -> Dict[str, Any]:
        """A new moment. First what her senses bring in is weighed against
        everything else (bottom-up) and a focus is picked. Then she asks the
        other lobes what they make of it, and weighs again with that."""
        from team import about_moment, words_of
        moment = content.get("moment") if isinstance(content.get("moment"), dict) else {}
        user_id = str(content.get("user_id") or moment.get("user_id") or "default")
        # What her senses bring in this moment, as Sensory Integration built it.
        signals: List[Dict[str, Any]] = [dict(item) for item in moment.get("attention_signals") or []
                                         if isinstance(item, dict)]
        # The one that carries the words, if any.
        sense = str(moment.get("modality") or "text")
        said = next((sig for sig in signals if words_of(moment) and str(sig.get("modality")) == sense), None)
        if said is not None:
            # How new Novelty found this moment.
            novelty = about_moment(self.thalamus, "novelty", content, "attention")
            said["novelty_score"] = novelty.get("novelty_score", novelty.get("score", 0.0))
            said.setdefault("user_id", user_id)
        # A new moment is a new thing: last moment's score for the same sense doesn't carry into it.
        self.remove_signals(ids=[str(sig.get("id")) for sig in signals if sig.get("id")])
        result = self.evaluate(signals)
        if result.get("focus"):
            self.route_focus()
        self.turn_up_focus()
        self._report_focus("a new moment (what her senses brought)")
        if said is not None:
            # What the other lobes make of it: whether it asks something or carries
            # feeling (Language), and how strongly she feels about it (Emotion).
            reading = about_moment(self.thalamus, "language", content, "attention").get("language_understanding")
            reading = reading if isinstance(reading, dict) else {}
            affect = reading.get("affect") if isinstance(reading.get("affect"), dict) else {}
            felt = about_moment(self.thalamus, "emotion", content, "attention")
            said.update(asks=reading.get("speech_act") == "question", feeling=bool(affect.get("present")),
                        felt=self._unit(felt.get("intensity")))
            self.replace_signals([said])
            if self.current_focus:
                self.route_focus()
            self.turn_up_focus()
            self._report_focus(f"what the other lobes made of it: asks={said['asks']}, "
                               f"feeling={said['feeling']}, felt={round(said['felt'], 3)}")
        return self.get_focus()

    def _report_focus(self, because: str) -> None:
        """For the tracer: where her focus is, and what just changed it."""
        meta = self.signal_meta.get(self.current_focus or "") or {}
        _trace("attention_focus", focus=self.current_focus, on=str(meta.get("text") or "")[:120],
               score=self.salience_map.get(self.current_focus or ""), because=because,
               competing=[{"id": r["id"], "score": r["score"]} for r in self.rank_signals()[:4]])

    def turn_up_focus(self) -> Dict[str, Any]:
        """Set the Thalamus's volume: what the lobes behind her current focus
        announce is delivered first; everything else is back to normal. The
        Thalamus only applies it."""
        set_volume = getattr(self.thalamus, "set_volume", None)
        if not callable(set_volume):
            return {}
        meta = self.signal_meta.get(self.current_focus or "") or {}
        winners = self._CARRIED_BY.get(str(meta.get("source") or "").lower(), ())
        levels = {f"from:{lobe}": 1.0 for lobe in getattr(self, "_turned_up", ())}
        levels.update({f"from:{lobe}": self._WINNER_VOLUME for lobe in winners})
        if not levels or levels == getattr(self, "_last_levels", None):
            return levels
        self._turned_up = tuple(winners)
        self._last_levels = dict(levels)
        set_volume(levels)
        return levels

    def get_focus(self) -> Dict[str, Any]:
        """Where her focus is right now, without weighing anything again."""
        ranked = self.rank_signals()
        entry = next((r for r in ranked if r.get("id") == self.current_focus), None)
        return {
            "focus": self.current_focus,
            "focus_text": (entry or {}).get("text"),
            "focus_score": (entry or {}).get("score"),
            "focus_source": (entry or {}).get("source"),
            "ranked": ranked,
            "salience_map": dict(self.salience_map),
        }

    def get_status(self) -> Dict[str, Any]:
        return {
            "current_focus": self.current_focus,
            "salience_count": len(self.salience_map),
            "decay_rate": self.decay_rate,
            "min_salience": self.min_salience,
            "evaluate_count": self._evaluate_count,
            "top": (self.rank_signals()[:3] if self.salience_map else []),
        }

    def reset(self) -> None:
        self.current_focus = None
        self.salience_map.clear()
        self.signal_meta.clear()
        self._last_decay_at = time.time()

    def state_now(self) -> Dict[str, Any]:
        """Where her focus is right now: shared with every lobe whenever it changes."""
        return self.get_focus()

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        if "content" in message and isinstance(message.get("content"), dict):
            content = message["content"]
        else:
            content = {
                k: v
                for k, v in message.items()
                if k not in ("type", "_message_id", "message_id", "source")
            }

        if msg_type in ("moment", "about_moment"):
            from team import nothing_more, take_moment
            return {"status": "success", "content": take_moment(self, "attention", self._take_in, content,
                                                               reads=("novelty", "language", "emotion"),
                                                               settle=nothing_more)}

        if msg_type == "get_focus":
            body = self.get_focus()
            return {"status": "success", "content": body}

        if msg_type in ("evaluate", "attend", "score_signals"):
            result = self.evaluate(content.get("signals", content.get("input_signals", [])))
            return {"status": "success", "content": result, **result}

        if msg_type in ("update_salience", "update"):
            ranked = self.update_salience(content.get("signals", []))
            return {
                "status": "success",
                "content": {"ranked": ranked, "salience_map": dict(self.salience_map)},
                "ranked": ranked,
            }

        if msg_type in ("replace_signals", "replace_salience", "replace"):
            ranked = self.replace_signals(content.get("signals", []))
            # What is competing changed: pick the focus again and pass it on.
            if self.select_focus():
                self.route_focus()
            self.turn_up_focus()
            self._report_focus("another lobe changed what is competing")
            return {
                "status": "success",
                "content": {"ranked": ranked, "salience_map": dict(self.salience_map)},
                "ranked": ranked,
            }

        if msg_type in ("remove_signals", "remove_signal", "drop_signals"):
            info = self.remove_signals(
                ids=content.get("ids", content.get("id")),
                prefix=content.get("prefix"),
            )
            return {
                "status": "success",
                "content": {**info, "salience_map": dict(self.salience_map)},
                **info,
            }

        if msg_type in ("select_focus", "focus"):
            focus = self.select_focus()
            meta = self.signal_meta.get(focus or "") or {}
            body = {
                "focus": focus,
                "focus_text": meta.get("text"),
                "score": self.salience_map.get(focus) if focus else None,
            }
            return {"status": "success", "content": body, **body}

        if msg_type in ("rank", "get_ranking"):
            ranked = self.rank_signals()
            return {"status": "success", "content": {"ranked": ranked}, "ranked": ranked}

        if msg_type == "decay":
            info = self.decay(force=True)
            return {"status": "success", "content": info, **info}

        if msg_type == "route_focus":
            routed = self.route_focus()
            return {"status": "success", "content": routed, **routed}

        if msg_type in ("get_status", "status"):
            status = self.get_status()
            return {"status": "success", "content": status, **status}

        if msg_type == "reset":
            self.reset()
            return {"status": "success", "content": {"message": "AttentionLobe reset"}}

        if msg_type == "health":
            return {"status": "success", "healthy": True, "content": {"healthy": True}}

        return {
            "status": "error",
            "message": f"Unknown message type: {msg_type}",
            "content": {},
        }
