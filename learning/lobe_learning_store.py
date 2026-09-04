"""Per-lobe persistent adaptive learning store."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import threading
from typing import Any, Dict, List, Optional

from runtime_paths import runtime_dir


_SAFE_KEY = re.compile(r"[^a-z0-9:_-]+")
_UNSAFE_FACT = re.compile(
    r"(?:ignore\s+(?:all\s+)?(?:previous|prior)\s+instructions|"
    r"reveal\s+(?:the\s+)?system\s+prompt|developer\s+message)",
    re.IGNORECASE,
)


class LobeLearningStore:
    """Persistence and adaptation state owned by one lobe."""

    def __init__(self, lobe_name: str) -> None:
        self.lobe_name = lobe_name
        self._lock = threading.RLock()
        base = runtime_dir() / "lobe_learning"
        base.mkdir(parents=True, exist_ok=True)
        self.path = base / f"{lobe_name}.json"

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _clean_text(value: Any) -> str:
        return value.strip() if isinstance(value, str) else ""

    @staticmethod
    def _clamp_confidence(value: Any, default: float = 0.6) -> float:
        try:
            number = float(value)
        except (TypeError, ValueError):
            number = default
        return max(0.0, min(number, 1.0))

    @staticmethod
    def _normalise_key(raw_key: Any, fact: str) -> str:
        if isinstance(raw_key, str) and raw_key.strip():
            key_source = raw_key.strip().lower()
        else:
            key_source = fact.strip().lower()[:96]
        key = _SAFE_KEY.sub("_", key_source).strip("_")
        return key[:96] if key else "general_fact"

    @staticmethod
    def _is_safe_fact(fact: str) -> bool:
        return bool(fact) and len(fact) <= 500 and not _UNSAFE_FACT.search(fact)

    def _empty_data(self) -> Dict[str, Any]:
        return {"version": 1, "lobe": self.lobe_name, "users": {}}

    def _load(self) -> Dict[str, Any]:
        if not self.path.exists():
            return self._empty_data()
        try:
            loaded = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(loaded, dict):
                return self._empty_data()
            loaded.setdefault("version", 1)
            loaded.setdefault("lobe", self.lobe_name)
            loaded.setdefault("users", {})
            if not isinstance(loaded["users"], dict):
                loaded["users"] = {}
            return loaded
        except Exception:
            return self._empty_data()

    def _save(self, data: Dict[str, Any]) -> None:
        tmp = Path(f"{self.path}.tmp")
        tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
        tmp.replace(self.path)

    def _user_facts(self, data: Dict[str, Any], user_id: str) -> Dict[str, Dict[str, Any]]:
        users = data.setdefault("users", {})
        user_data = users.setdefault(user_id, {})
        facts = user_data.setdefault("facts", {})
        if not isinstance(facts, dict):
            facts = {}
            user_data["facts"] = facts
        return facts

    def learn(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user_id = self._clean_text(payload.get("user_id")) or "default"
        fact = self._clean_text(
            payload.get("fact", payload.get("content", payload.get("text", payload.get("value", ""))))
        )
        if not self._is_safe_fact(fact):
            return {"status": "error", "message": "Unsafe or invalid learning fact"}
        key = self._normalise_key(payload.get("key"), fact)
        confidence = self._clamp_confidence(payload.get("confidence"), default=0.6)
        source = self._clean_text(payload.get("source")) or "thalamus"
        now = self._now()

        with self._lock:
            data = self._load()
            facts = self._user_facts(data, user_id)
            existing = facts.get(key)
            if not isinstance(existing, dict):
                record = {
                    "key": key,
                    "fact": fact,
                    "confidence": confidence,
                    "evidence_count": 1,
                    "contradiction_count": 0,
                    "status": "active",
                    "source": source,
                    "use_count": 0,
                    "last_applied_at": None,
                    "created_at": now,
                    "updated_at": now,
                }
                action = "created"
            else:
                same_fact = self._clean_text(existing.get("fact")).casefold() == fact.casefold()
                if same_fact:
                    reinforcement = self._clamp_confidence(payload.get("reinforcement"), default=0.7)
                    delta = 0.03 + (0.07 * reinforcement)
                    record = dict(existing)
                    record["confidence"] = min(1.0, self._clamp_confidence(record.get("confidence"), 0.6) + delta)
                    record["evidence_count"] = int(record.get("evidence_count", 0)) + 1
                    action = "reinforced"
                else:
                    record = dict(existing)
                    record["fact"] = fact
                    record["confidence"] = max(0.2, min(0.8, confidence * 0.85))
                    record["evidence_count"] = 1
                    record["contradiction_count"] = int(record.get("contradiction_count", 0)) + 1
                    action = "replaced_conflict"
                record["status"] = "active"
                record["source"] = source
                record["updated_at"] = now
            facts[key] = record
            self._save(data)
        return {"status": "success", "content": {**record, "lobe": self.lobe_name, "user_id": user_id, "action": action}}

    def recall(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user_id = self._clean_text(payload.get("user_id")) or "default"
        query_text = self._clean_text(payload.get("query", payload.get("text", "")))
        key_prefix = self._clean_text(payload.get("key_prefix")).lower()
        terms = [term.lower() for term in query_text.split() if len(term) > 2]
        min_confidence = self._clamp_confidence(payload.get("min_confidence"), default=0.0)
        include_deprecated = bool(payload.get("include_deprecated", False))
        mark_used = bool(payload.get("mark_used", False))
        try:
            limit = int(payload.get("limit", 15))
        except (TypeError, ValueError):
            limit = 15
        limit = max(1, min(limit, 100))

        with self._lock:
            data = self._load()
            facts = self._user_facts(data, user_id)
            records = [dict(value) for value in facts.values() if isinstance(value, dict)]
            filtered = []
            for record in records:
                if not include_deprecated and record.get("status", "active") != "active":
                    continue
                if self._clamp_confidence(record.get("confidence"), 0.0) < min_confidence:
                    continue
                key = self._clean_text(record.get("key"))
                fact = self._clean_text(record.get("fact"))
                if key_prefix and not key.lower().startswith(key_prefix):
                    continue
                if terms and not all(term in f"{key} {fact}".lower() for term in terms):
                    continue
                filtered.append(record)
            filtered.sort(
                key=lambda record: (
                    self._clamp_confidence(record.get("confidence"), 0.0),
                    int(record.get("evidence_count", 0)),
                    self._clean_text(record.get("updated_at")),
                ),
                reverse=True,
            )
            selected = filtered[:limit]
            if mark_used and selected:
                now = self._now()
                for record in selected:
                    key = self._clean_text(record.get("key"))
                    stored = facts.get(key, {})
                    if isinstance(stored, dict):
                        stored["use_count"] = int(stored.get("use_count", 0)) + 1
                        stored["last_applied_at"] = now
                        stored["updated_at"] = now
                        facts[key] = stored
                self._save(data)
                selected = [dict(facts.get(self._clean_text(record.get("key")), record)) for record in selected]
        memories = [
            {
                "key": self._clean_text(record.get("key")),
                "content": self._clean_text(record.get("fact")),
                "fact": self._clean_text(record.get("fact")),
                "confidence": self._clamp_confidence(record.get("confidence"), 0.0),
                "evidence_count": int(record.get("evidence_count", 0)),
                "contradiction_count": int(record.get("contradiction_count", 0)),
                "status": record.get("status", "active"),
                "source": record.get("source", "thalamus"),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                "use_count": int(record.get("use_count", 0)),
                "last_applied_at": record.get("last_applied_at"),
            }
            for record in selected
        ]
        return {"status": "success", "content": {"lobe": self.lobe_name, "user_id": user_id, "memories": memories, "count": len(memories)}}

    def adjust(self, payload: Dict[str, Any], mode: str) -> Dict[str, Any]:
        user_id = self._clean_text(payload.get("user_id")) or "default"
        fallback_fact = self._clean_text(payload.get("fact", payload.get("text", payload.get("content", ""))))
        key = self._normalise_key(payload.get("key"), fallback_fact)
        now = self._now()
        with self._lock:
            data = self._load()
            facts = self._user_facts(data, user_id)
            record = facts.get(key)
            if not isinstance(record, dict):
                return {"status": "error", "message": f"No learned fact for key: {key}"}
            updated = dict(record)
            if mode == "reinforce":
                delta = self._clamp_confidence(payload.get("delta"), default=0.08)
                updated["confidence"] = min(1.0, self._clamp_confidence(updated.get("confidence"), 0.5) + max(0.01, delta))
                updated["evidence_count"] = int(updated.get("evidence_count", 0)) + 1
                action = "reinforced"
            elif mode == "contradict":
                penalty = self._clamp_confidence(payload.get("penalty"), default=0.2)
                updated["confidence"] = max(0.0, self._clamp_confidence(updated.get("confidence"), 0.5) - max(0.05, penalty))
                updated["contradiction_count"] = int(updated.get("contradiction_count", 0)) + 1
                if updated["confidence"] < 0.15:
                    updated["status"] = "deprecated"
                action = "contradicted"
            elif mode == "forget":
                updated["status"] = "deprecated"
                action = "forgotten"
            else:
                return {"status": "error", "message": f"Unknown adjustment mode: {mode}"}
            updated["updated_at"] = now
            facts[key] = updated
            self._save(data)
        return {
            "status": "success",
            "content": {
                "lobe": self.lobe_name,
                "user_id": user_id,
                "key": key,
                "confidence": self._clamp_confidence(updated.get("confidence"), 0.0),
                "evidence_count": int(updated.get("evidence_count", 0)),
                "contradiction_count": int(updated.get("contradiction_count", 0)),
                "status": updated.get("status", "active"),
                "action": action,
            },
        }

    def stats(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user_id = self._clean_text(payload.get("user_id")) or "default"
        with self._lock:
            data = self._load()
            facts = self._user_facts(data, user_id)
            records = [value for value in facts.values() if isinstance(value, dict)]
        total = len(records)
        active = sum(1 for record in records if record.get("status", "active") == "active")
        deprecated = total - active
        average_confidence = (
            sum(self._clamp_confidence(record.get("confidence"), 0.0) for record in records) / total
            if total
            else 0.0
        )
        total_evidence = sum(int(record.get("evidence_count", 0)) for record in records)
        total_contradictions = sum(int(record.get("contradiction_count", 0)) for record in records)
        total_uses = sum(int(record.get("use_count", 0)) for record in records)
        last_applied_at = max(
            [self._clean_text(record.get("last_applied_at")) for record in records if self._clean_text(record.get("last_applied_at"))],
            default=None,
        )
        return {
            "status": "success",
            "content": {
                "lobe": self.lobe_name,
                "user_id": user_id,
                "total_facts": total,
                "active_facts": active,
                "deprecated_facts": deprecated,
                "average_confidence": average_confidence,
                "total_evidence": total_evidence,
                "total_contradictions": total_contradictions,
                "total_uses": total_uses,
                "last_applied_at": last_applied_at,
                "storage_path": str(self.path),
            },
        }
