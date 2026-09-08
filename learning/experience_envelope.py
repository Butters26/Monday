"""Versioned learning-experience envelope for cross-lobe learning events."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import uuid
from typing import Any, Dict, List, Optional


SUPPORTED_SCHEMA_VERSION = 1
ALLOWED_EVENT_TYPES = {
    "explicit_lesson",
    "experience",
    "correction",
    "reflection",
    "outcome",
}


def _clean_text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _clean_list(values: Any) -> List[str]:
    if not isinstance(values, list):
        return []
    return [item.strip() for item in values if isinstance(item, str) and item.strip()]


@dataclass
class ExperienceEnvelope:
    """Transport envelope shared by all learning-capable lobes."""

    schema_version: int = SUPPORTED_SCHEMA_VERSION
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    correlation_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    event_type: str = "experience"
    source: str = "user"
    user_id: str = "default"
    raw_experience: str = ""
    conversation_context: List[str] = field(default_factory=list)
    examples: List[str] = field(default_factory=list)
    counterexamples: List[str] = field(default_factory=list)
    feedback: str = ""
    observed_outcome: str = ""
    confidence: float = 0.5
    uncertainty: float = 0.5
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    supporting_memory_ids: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_payload(
        cls, payload: Dict[str, Any], source: str = "thalamus"
    ) -> "ExperienceEnvelope":
        data = payload if isinstance(payload, dict) else {}
        event_type = _clean_text(data.get("event_type")) or (
            "explicit_lesson" if _clean_text(data.get("lesson")) else "experience"
        )
        if event_type not in ALLOWED_EVENT_TYPES:
            event_type = "experience"
        raw_experience = _clean_text(
            data.get("raw_experience", data.get("lesson", data.get("text", "")))
        )
        confidence = data.get("confidence", 0.5)
        uncertainty = data.get("uncertainty", 1.0 - float(confidence or 0.5))
        try:
            confidence = float(confidence)
        except (TypeError, ValueError):
            confidence = 0.5
        try:
            uncertainty = float(uncertainty)
        except (TypeError, ValueError):
            uncertainty = 0.5
        confidence = max(0.0, min(1.0, confidence))
        uncertainty = max(0.0, min(1.0, uncertainty))
        if confidence + uncertainty > 1.0:
            total = confidence + uncertainty
            confidence = confidence / total
            uncertainty = uncertainty / total
        return cls(
            schema_version=int(data.get("schema_version", SUPPORTED_SCHEMA_VERSION)),
            event_id=_clean_text(data.get("event_id")) or str(uuid.uuid4()),
            correlation_id=_clean_text(data.get("correlation_id")) or str(uuid.uuid4()),
            event_type=event_type,
            source=_clean_text(data.get("source")) or source,
            user_id=_clean_text(data.get("user_id")) or "default",
            raw_experience=raw_experience,
            conversation_context=_clean_list(data.get("conversation_context")),
            examples=_clean_list(data.get("examples")),
            counterexamples=_clean_list(data.get("counterexamples")),
            feedback=_clean_text(data.get("feedback")),
            observed_outcome=_clean_text(data.get("observed_outcome")),
            confidence=confidence,
            uncertainty=uncertainty,
            timestamp=_clean_text(data.get("timestamp"))
            or datetime.now(timezone.utc).isoformat(),
            supporting_memory_ids=_clean_list(data.get("supporting_memory_ids")),
            metadata=data.get("metadata", {}) if isinstance(data.get("metadata"), dict) else {},
        )

    def validate(self) -> Optional[str]:
        if self.schema_version != SUPPORTED_SCHEMA_VERSION:
            return f"Unsupported schema_version {self.schema_version}"
        if self.event_type not in ALLOWED_EVENT_TYPES:
            return f"Unsupported event_type {self.event_type}"
        if not self.event_id:
            return "event_id is required"
        if not self.correlation_id:
            return "correlation_id is required"
        if not self.user_id:
            return "user_id is required"
        if not self.raw_experience:
            return "raw_experience is required"
        return None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "event_id": self.event_id,
            "correlation_id": self.correlation_id,
            "event_type": self.event_type,
            "source": self.source,
            "user_id": self.user_id,
            "raw_experience": self.raw_experience,
            "conversation_context": list(self.conversation_context),
            "examples": list(self.examples),
            "counterexamples": list(self.counterexamples),
            "feedback": self.feedback,
            "observed_outcome": self.observed_outcome,
            "confidence": self.confidence,
            "uncertainty": self.uncertainty,
            "timestamp": self.timestamp,
            "supporting_memory_ids": list(self.supporting_memory_ids),
            "metadata": dict(self.metadata),
        }
