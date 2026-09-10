"""Per-lobe persistent adaptive learning store."""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
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

    def __init__(self, lobe_name: str, runtime_directory: Optional[Path] = None) -> None:
        self.lobe_name = lobe_name
        self._lock = threading.RLock()
        base_root = runtime_directory if isinstance(runtime_directory, Path) else runtime_dir()
        base = base_root / "lobe_learning"
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

    @staticmethod
    def _safe_list(value: Any) -> List[str]:
        if not isinstance(value, list):
            return []
        cleaned: List[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                cleaned.append(item.strip())
        return cleaned[:20]

    @staticmethod
    def _tokens(text: str) -> set[str]:
        return {token for token in re.findall(r"[a-z0-9]{3,}", text.lower())}

    def _normalise_learning_record(
        self, payload: Dict[str, Any], fact: str, source: str, confidence: float
    ) -> Dict[str, Any]:
        record = payload.get("record", {})
        record = dict(record) if isinstance(record, dict) else {}
        record_type = self._clean_text(record.get("type", payload.get("record_type", "fact"))).lower() or "fact"
        subject = self._clean_text(record.get("subject", payload.get("subject", self.lobe_name)))
        relation = self._clean_text(record.get("relation", payload.get("relation", "guidance")))
        input_value = record.get("input", payload.get("input"))
        if isinstance(input_value, list):
            learned_input = [self._clean_text(item) for item in input_value if self._clean_text(item)]
        elif isinstance(input_value, str):
            learned_input = [input_value.strip()]
        else:
            learned_input = []
        value = self._clean_text(record.get("value", fact))
        scope = self._clean_text(record.get("scope", payload.get("scope", "general"))).lower() or "general"
        status = self._clean_text(record.get("status", "provisional")).lower() or "provisional"
        if status not in {"proposed", "provisional", "validated", "active", "disputed", "deprecated"}:
            status = "provisional"
        return {
            "type": record_type,
            "subject": subject,
            "relation": relation,
            "input": learned_input,
            "value": value,
            "scope": scope,
            "confidence": confidence,
            "source": self._clean_text(record.get("source", source)) or source,
            "examples": self._safe_list(record.get("examples", payload.get("examples", []))),
            "exceptions": self._safe_list(record.get("exceptions", payload.get("exceptions", []))),
            "status": status,
            "evidence": self._safe_list(record.get("evidence", payload.get("evidence", []))),
            "conflict_status": self._clean_text(record.get("conflict_status", "none")).lower() or "none",
        }

    def _empty_data(self) -> Dict[str, Any]:
        return {"version": 1, "lobe": self.lobe_name, "users": {}}

    def _backup_path(self) -> Path:
        return Path(f"{self.path}.bak")

    def _normalise_loaded(self, loaded: Any) -> Optional[Dict[str, Any]]:
        if not isinstance(loaded, dict):
            return None
        loaded.setdefault("version", 1)
        loaded.setdefault("lobe", self.lobe_name)
        loaded.setdefault("users", {})
        if not isinstance(loaded["users"], dict):
            loaded["users"] = {}
        return loaded

    def _load(self) -> Dict[str, Any]:
        candidate_paths = [self.path, self._backup_path()]
        for index, path in enumerate(candidate_paths):
            if not path.exists():
                continue
            try:
                loaded = json.loads(path.read_text(encoding="utf-8"))
                normalised = self._normalise_loaded(loaded)
                if normalised is None:
                    continue
                if index == 1:
                    try:
                        self.path.write_text(
                            json.dumps(normalised, indent=2, sort_keys=True),
                            encoding="utf-8",
                        )
                    except Exception:
                        pass
                return normalised
            except Exception:
                continue
        return self._empty_data()

    def _save(self, data: Dict[str, Any]) -> None:
        normalised = self._normalise_loaded(data)
        if normalised is None:
            normalised = self._empty_data()
        try:
            if self.path.exists():
                shutil.copy2(self.path, self._backup_path())
        except Exception:
            pass
        tmp = Path(f"{self.path}.tmp")
        tmp.write_text(json.dumps(normalised, indent=2, sort_keys=True), encoding="utf-8")
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
        learning_record = self._normalise_learning_record(payload, fact, source, confidence)
        required_evidence = payload.get("required_evidence", [])
        required_evidence = required_evidence if isinstance(required_evidence, list) else []

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
                    "status": learning_record.get("status", "provisional"),
                    "source": source,
                    "use_count": 0,
                    "last_applied_at": None,
                    "accepted_at": None,
                    "learning_record": learning_record,
                    "required_evidence": required_evidence,
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
                    lifecycle = self._clean_text(record.get("status")).lower() or "provisional"
                    if lifecycle in {"proposed", "provisional"} and record["evidence_count"] >= 2:
                        lifecycle = "validated"
                        record["accepted_at"] = now
                    if lifecycle == "validated" and record["evidence_count"] >= 3:
                        lifecycle = "active"
                    record["status"] = lifecycle
                    action = "reinforced"
                else:
                    record = dict(existing)
                    conflicts = record.get("conflicts", [])
                    conflicts = conflicts if isinstance(conflicts, list) else []
                    conflicts.append(
                        {
                            "fact": fact,
                            "source": source,
                            "confidence": confidence,
                            "created_at": now,
                            "record": learning_record,
                        }
                    )
                    record["conflicts"] = conflicts[-20:]
                    record["contradiction_count"] = int(record.get("contradiction_count", 0)) + 1
                    record["status"] = "disputed"
                    action = "pending_conflict"
                record["source"] = source
                record["updated_at"] = now
                if action != "pending_conflict":
                    record["fact"] = fact
                    record["learning_record"] = learning_record
                    record["required_evidence"] = required_evidence
            facts[key] = record
            self._save(data)
        return {"status": "success", "content": {**record, "lobe": self.lobe_name, "user_id": user_id, "action": action}}

    def recall(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        user_id = self._clean_text(payload.get("user_id")) or "default"
        query_text = self._clean_text(payload.get("query", payload.get("text", "")))
        key_prefix = self._clean_text(payload.get("key_prefix")).lower()
        terms = self._tokens(query_text)
        min_confidence = self._clamp_confidence(payload.get("min_confidence"), default=0.0)
        include_deprecated = bool(payload.get("include_deprecated", False))
        include_disputed = bool(payload.get("include_disputed", False))
        mark_used = bool(payload.get("mark_used", False))
        scope = self._clean_text(payload.get("scope")).lower()
        record_type = self._clean_text(payload.get("record_type")).lower()
        subject = self._clean_text(payload.get("subject")).lower()
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
                    status = self._clean_text(record.get("status")).lower()
                    if status == "deprecated":
                        continue
                    if status == "disputed" and not include_disputed:
                        continue
                if self._clamp_confidence(record.get("confidence"), 0.0) < min_confidence:
                    continue
                key = self._clean_text(record.get("key"))
                fact = self._clean_text(record.get("fact"))
                if key_prefix and not key.lower().startswith(key_prefix):
                    continue
                structured = record.get("learning_record", {})
                structured = structured if isinstance(structured, dict) else {}
                if scope and self._clean_text(structured.get("scope")).lower() not in {"", scope}:
                    continue
                if record_type and self._clean_text(structured.get("type")).lower() not in {"", record_type}:
                    continue
                if subject and subject not in self._clean_text(structured.get("subject")).lower():
                    continue
                relevance = 0.0
                if terms:
                    haystack = self._tokens(
                        " ".join(
                            [
                                key,
                                fact,
                                self._clean_text(structured.get("subject")),
                                self._clean_text(structured.get("relation")),
                                self._clean_text(structured.get("value")),
                                " ".join(self._safe_list(structured.get("examples"))),
                            ]
                        )
                    )
                    matched_terms = sum(1 for term in terms if term in haystack)
                    if matched_terms == 0:
                        continue
                    relevance = matched_terms / len(terms)
                evidence_score = min(1.0, int(record.get("evidence_count", 0)) / 5.0)
                recency_bonus = 0.1 if self._clean_text(record.get("updated_at")) else 0.0
                conflict_penalty = 0.25 if self._clean_text(record.get("status")).lower() == "disputed" else 0.0
                confidence = self._clamp_confidence(record.get("confidence"), 0.0)
                record["_score"] = relevance + (0.35 * confidence) + (0.2 * evidence_score) + recency_bonus - conflict_penalty
                record["_relevance"] = relevance
                filtered.append(record)
            filtered.sort(
                key=lambda record: (
                    float(record.get("_score", 0.0)),
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
                "learning_record": record.get("learning_record", {}),
                "created_at": record.get("created_at"),
                "updated_at": record.get("updated_at"),
                "use_count": int(record.get("use_count", 0)),
                "last_applied_at": record.get("last_applied_at"),
                "retrieved": True,
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
                if not bool(payload.get("valid_correction", False)):
                    updated["updated_at"] = now
                    return {
                        "status": "error",
                        "message": "Contradiction rejected: missing valid correction evidence",
                        "content": {
                            "lobe": self.lobe_name,
                            "user_id": user_id,
                            "key": key,
                            "status": updated.get("status", "active"),
                            "action": "contradiction_rejected",
                        },
                    }
                penalty = self._clamp_confidence(payload.get("penalty"), default=0.2)
                updated["confidence"] = max(0.0, self._clamp_confidence(updated.get("confidence"), 0.5) - max(0.05, penalty))
                updated["contradiction_count"] = int(updated.get("contradiction_count", 0)) + 1
                correction_fact = self._clean_text(payload.get("correction_fact"))
                if correction_fact:
                    updated["fact"] = correction_fact
                    updated["status"] = "provisional"
                    updated["accepted_at"] = None
                    action = "corrected_replace"
                else:
                    updated["status"] = "deprecated" if updated["confidence"] < 0.15 else "disputed"
                    action = "contradicted"
                if updated["confidence"] < 0.15:
                    updated["status"] = "deprecated"
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
        lifecycle_counts = {
            "proposed": 0,
            "provisional": 0,
            "validated": 0,
            "active": 0,
            "disputed": 0,
            "deprecated": 0,
        }
        for record in records:
            status = self._clean_text(record.get("status")).lower() or "provisional"
            if status in lifecycle_counts:
                lifecycle_counts[status] += 1
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
                "lifecycle_counts": lifecycle_counts,
                "last_applied_at": last_applied_at,
                "storage_path": str(self.path),
            },
        }
