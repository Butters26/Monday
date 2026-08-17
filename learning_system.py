"""Learning system for Monday's direct core.

Implements an observe -> store -> evaluate -> adapt loop with:
- short-term session memory (in-process ring buffer)
- long-term persisted memory (SQLite in runtime storage)
- explicit and implicit feedback signals
- safety controls (forget/override/confidence bounds/audit trail)
- evaluation gates (quality trend metrics)
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
import threading
from typing import Any, Deque, Dict, List, Optional

from runtime_paths import runtime_file


@dataclass
class LearningEvent:
    user_id: str
    user_input: str
    response_text: str
    quality_score: float
    created_at: str


class LearningSystem:
    """Persist and evaluate lightweight user-scoped learning signals."""

    def __init__(self, storage_path: Optional[str] = None, short_term_limit: int = 50) -> None:
        self.running = True
        self.storage_path = storage_path or runtime_file("learning_memory.sqlite3")
        Path(self.storage_path).expanduser().resolve().parent.mkdir(parents=True, exist_ok=True)
        self.short_term: Deque[LearningEvent] = deque(maxlen=max(10, short_term_limit))
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.storage_path, check_same_thread=False)
        self._init_schema()

    def _init_schema(self) -> None:
        with self._lock:
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS learning_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    user_input TEXT NOT NULL,
                    response_text TEXT NOT NULL,
                    quality_score REAL NOT NULL,
                    intent TEXT,
                    confidence REAL,
                    created_at TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS feedback_events (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    feedback_score REAL NOT NULL,
                    reason TEXT,
                    created_at TEXT NOT NULL
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS preference_overrides (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    pref_key TEXT NOT NULL,
                    pref_value TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    updated_at TEXT NOT NULL,
                    UNIQUE(user_id, pref_key)
                )"""
            )
            self._connection.execute(
                """CREATE TABLE IF NOT EXISTS learning_audit_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id TEXT NOT NULL,
                    action TEXT NOT NULL,
                    details TEXT,
                    created_at TEXT NOT NULL
                )"""
            )
            self._connection.commit()

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _clamp_confidence(value: Any, default: float = 0.5) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(0.0, min(1.0, parsed))

    @staticmethod
    def _clamp_feedback(value: Any, default: float = 0.0) -> float:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            parsed = default
        return max(-1.0, min(1.0, parsed))

    @staticmethod
    def _quality_from_response(response_text: str) -> float:
        if not isinstance(response_text, str) or not response_text.strip():
            return 0.0
        if response_text.strip() == "I am unable to formulate a response right now.":
            return 0.0
        return 1.0

    def _audit(self, user_id: str, action: str, details: str = "") -> None:
        with self._lock:
            self._connection.execute(
                "INSERT INTO learning_audit_log(user_id, action, details, created_at) VALUES (?, ?, ?, ?)",
                (user_id, action, details, self._now()),
            )
            self._connection.commit()

    def record_interaction(
        self,
        user_id: str,
        user_input: str,
        response_text: str,
        intent: str = "conversation",
        confidence: float = 0.5,
        quality_score: Optional[float] = None,
    ) -> Dict[str, Any]:
        if not isinstance(user_id, str) or not user_id.strip():
            return {"status": "error", "message": "user_id must be a non-empty string"}
        if not isinstance(user_input, str):
            user_input = ""
        if not isinstance(response_text, str):
            response_text = ""
        confidence = self._clamp_confidence(confidence)
        score = self._quality_from_response(response_text) if quality_score is None else self._clamp_confidence(quality_score)
        created_at = self._now()
        event = LearningEvent(
            user_id=user_id,
            user_input=user_input.strip(),
            response_text=response_text.strip(),
            quality_score=score,
            created_at=created_at,
        )
        self.short_term.append(event)
        with self._lock:
            self._connection.execute(
                "INSERT INTO learning_events(user_id, user_input, response_text, quality_score, intent, confidence, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)",
                (user_id, event.user_input, event.response_text, score, intent, confidence, created_at),
            )
            self._connection.commit()
        self._audit(user_id, "record_interaction", f"intent={intent},quality={score}")
        return {"status": "success", "content": {"quality_score": score}}

    def record_feedback(self, user_id: str, feedback_score: Any, reason: str = "") -> Dict[str, Any]:
        if not isinstance(user_id, str) or not user_id.strip():
            return {"status": "error", "message": "user_id must be a non-empty string"}
        score = self._clamp_feedback(feedback_score)
        with self._lock:
            self._connection.execute(
                "INSERT INTO feedback_events(user_id, feedback_score, reason, created_at) VALUES (?, ?, ?, ?)",
                (user_id, score, reason[:1000] if isinstance(reason, str) else "", self._now()),
            )
            self._connection.commit()
        self._audit(user_id, "record_feedback", f"score={score}")
        return {"status": "success", "content": {"feedback_score": score}}

    def set_preference_override(
        self, user_id: str, pref_key: str, pref_value: str, confidence: Any = 0.9
    ) -> Dict[str, Any]:
        if not all(isinstance(value, str) and value.strip() for value in (user_id, pref_key, pref_value)):
            return {"status": "error", "message": "user_id, pref_key, and pref_value are required"}
        bounded = self._clamp_confidence(confidence, default=0.9)
        with self._lock:
            self._connection.execute(
                """INSERT INTO preference_overrides(user_id, pref_key, pref_value, confidence, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, pref_key) DO UPDATE SET
                       pref_value = excluded.pref_value,
                       confidence = excluded.confidence,
                       updated_at = excluded.updated_at""",
                (user_id, pref_key.strip(), pref_value.strip(), bounded, self._now()),
            )
            self._connection.commit()
        self._audit(user_id, "set_preference_override", f"{pref_key}={pref_value}")
        return {"status": "success", "content": {"pref_key": pref_key.strip(), "pref_value": pref_value.strip(), "confidence": bounded}}

    def forget_user_data(self, user_id: str) -> Dict[str, Any]:
        if not isinstance(user_id, str) or not user_id.strip():
            return {"status": "error", "message": "user_id must be a non-empty string"}
        with self._lock:
            self._connection.execute("DELETE FROM learning_events WHERE user_id = ?", (user_id,))
            self._connection.execute("DELETE FROM feedback_events WHERE user_id = ?", (user_id,))
            self._connection.execute("DELETE FROM preference_overrides WHERE user_id = ?", (user_id,))
            self._connection.execute("DELETE FROM learning_audit_log WHERE user_id = ?", (user_id,))
            self._connection.commit()
        self.short_term = deque([event for event in self.short_term if event.user_id != user_id], maxlen=self.short_term.maxlen)
        return {"status": "success", "content": {"forgotten_user_id": user_id}}

    def _preference_rows(self, user_id: str) -> List[Dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT pref_key, pref_value, confidence, updated_at FROM preference_overrides WHERE user_id = ?",
                (user_id,),
            ).fetchall()
        return [
            {"key": key, "value": value, "confidence": conf, "updated_at": updated_at}
            for key, value, conf, updated_at in rows
        ]

    def get_adaptation_context(self, user_id: str) -> Dict[str, Any]:
        prefs = self._preference_rows(user_id)
        preference_map = {item["key"]: item["value"] for item in prefs}
        return {
            "preferences": preference_map,
            "preference_confidence": {item["key"]: item["confidence"] for item in prefs},
            "short_term_events": [
                {
                    "user_input": event.user_input,
                    "response_text": event.response_text,
                    "quality_score": event.quality_score,
                    "created_at": event.created_at,
                }
                for event in list(self.short_term)
                if event.user_id == user_id
            ][-10:],
        }

    def get_status(self, user_id: str = "default") -> Dict[str, Any]:
        with self._lock:
            events_count = self._connection.execute(
                "SELECT COUNT(*) FROM learning_events WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
            feedback_count = self._connection.execute(
                "SELECT COUNT(*) FROM feedback_events WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
            average_quality_row = self._connection.execute(
                "SELECT AVG(quality_score) FROM learning_events WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            average_feedback_row = self._connection.execute(
                "SELECT AVG(feedback_score) FROM feedback_events WHERE user_id = ?",
                (user_id,),
            ).fetchone()
            recent_quality_rows = self._connection.execute(
                "SELECT quality_score FROM learning_events WHERE user_id = ? ORDER BY id DESC LIMIT 10",
                (user_id,),
            ).fetchall()
            older_quality_rows = self._connection.execute(
                "SELECT quality_score FROM learning_events WHERE user_id = ? ORDER BY id DESC LIMIT 20 OFFSET 10",
                (user_id,),
            ).fetchall()
            audit_count = self._connection.execute(
                "SELECT COUNT(*) FROM learning_audit_log WHERE user_id = ?",
                (user_id,),
            ).fetchone()[0]
        avg_quality = float(average_quality_row[0]) if average_quality_row and average_quality_row[0] is not None else 0.0
        avg_feedback = float(average_feedback_row[0]) if average_feedback_row and average_feedback_row[0] is not None else 0.0
        recent_quality = [float(row[0]) for row in recent_quality_rows]
        older_quality = [float(row[0]) for row in older_quality_rows]
        recent_avg = sum(recent_quality) / len(recent_quality) if recent_quality else 0.0
        older_avg = sum(older_quality) / len(older_quality) if older_quality else recent_avg
        improving = recent_avg >= older_avg
        return {
            "status": "success",
            "content": {
                "user_id": user_id,
                "interactions": events_count,
                "feedback_events": feedback_count,
                "average_quality": round(avg_quality, 3),
                "average_feedback": round(avg_feedback, 3),
                "improving": improving,
                "preferences": self._preference_rows(user_id),
                "audit_events": audit_count,
            },
        }

    def shutdown(self) -> None:
        self.running = False
        with self._lock:
            if self._connection is not None:
                self._connection.close()
                self._connection = None
