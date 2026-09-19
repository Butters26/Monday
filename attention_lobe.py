"""AttentionLobe: selective focus for Monday's live path.

Scores salience of competing signals, decays stale scores, and returns an
honest ranked focus for thalamus — not print theater, not hardcoded dead routes.
"""

from __future__ import annotations

import time
from typing import Any, Dict, List, Optional, Tuple


# Urgency / affect cues that honestly raise salience (word-level, not theater).
_URGENCY_WORDS = frozenset(
    {
        "urgent",
        "important",
        "emergency",
        "help",
        "asap",
        "critical",
        "danger",
        "hurt",
        "scared",
        "afraid",
        "panic",
        "please",
    }
)
_AFFECT_WORDS = frozenset(
    {
        "love",
        "hate",
        "angry",
        "sad",
        "happy",
        "worried",
        "anxious",
        "excited",
        "lonely",
        "afraid",
        "terrified",
        "devastated",
        "furious",
    }
)
_QUESTION_CUES = frozenset(
    {"what", "why", "how", "when", "where", "who", "which", "?"}
)


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
            norm: Dict[str, Any] = {
                "id": AttentionLobe._signal_id(signal, index),
                "text": text,
                "source": str(signal.get("source") or "unknown"),
                "modality": str(signal.get("modality") or "text"),
                "priority": float(signal.get("priority") or signal.get("base_priority") or 0.0),
                "novelty_flags": list(signal.get("novelty_flags") or []),
                "emotions": list(signal.get("emotions") or []),
                "entities": list(signal.get("entities") or []),
                "concepts": list(signal.get("concepts") or signal.get("words") or []),
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
            "emotions": [],
            "entities": [],
            "concepts": [],
            "raw": signal,
        }

    def _compute_salience(self, signal: Dict[str, Any]) -> float:
        """Honest salience from signal properties (0.0–~1.5, uncapped then clipped)."""
        text = (signal.get("text") or "").strip()
        lower = text.lower()
        tokens = set(lower.replace("?", " ? ").split())
        score = 0.15  # baseline so empty-ish signals still exist briefly

        # Caller-supplied priority (0–1).
        try:
            score += min(1.0, max(0.0, float(signal.get("priority") or 0.0))) * 0.45
        except (TypeError, ValueError):
            pass

        # Source priors: live user input outranks ambient/system.
        source = str(signal.get("source") or "").lower()
        if source in {"user", "user_input", "chat"}:
            score += 0.35
        elif source in {"perception", "sensory"}:
            score += 0.20
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

        emotions = signal.get("emotions") or []
        if emotions:
            score += min(0.30, 0.10 * len(emotions))

        entities = signal.get("entities") or []
        if entities:
            score += min(0.20, 0.05 * len(entities))

        # Lexical urgency / affect / questions.
        if tokens & _URGENCY_WORDS:
            score += 0.35
        if tokens & _AFFECT_WORDS:
            score += 0.20
        if ("?" in text) or (tokens & _QUESTION_CUES):
            score += 0.15
        if "important" in lower:
            score += 0.25

        # Mild length signal — capped so length alone cannot dominate.
        if text:
            score += min(0.15, len(text) / 400.0)

        return round(min(1.5, max(0.0, score)), 4)

    # --- public API --------------------------------------------------------

    def decay(self, force: bool = False) -> Dict[str, Any]:
        """Multiply stored scores by (1 - decay_rate); prune below min_salience."""
        now = time.time()
        # Always allow explicit decay; evaluate also calls this each turn.
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
        """Decay → update → select. One-shot live-path attention pass."""
        decay_info = self.decay()
        ranked = self.update_salience(input_signals)
        focus_id = self.select_focus()
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
        send = getattr(self.thalamus, "send_message", None)
        if not callable(send):
            return {"routed": False, "reason": "thalamus_has_no_send", "payload": payload}
        # Only deliver if reasoning is actually registered — no hardcoded dead route.
        handlers = getattr(self.thalamus, "lobe_handlers", None) or {}
        if "reasoning" not in handlers:
            return {"routed": False, "reason": "reasoning_offline", "payload": payload}
        response = send(
            "reasoning",
            "attention_focus",
            payload,
            source="attention",
        )
        return {
            "routed": response.get("status") == "success",
            "response": response,
            "payload": payload,
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
