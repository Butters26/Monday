import logging
import math
from collections.abc import Mapping
from typing import Any, Dict, Set


logger = logging.getLogger(__name__)


class DataChecker:
    """Validate grounding metadata and filter configured output markers."""

    banned_phrases = {
        "well...",
        "um...",
        "as an ai",
        "i'm sorry, but",
        "i cannot fulfill",
        "it is important to note",
    }
    protected_core_keys = {
        "core_daemon",
        "thalamus_router",
        "socket_path",
        "reasoning_engine",
        "coaster_core",
    }

    @staticmethod
    def _count(payload: Mapping[str, Any], key: str) -> int:
        value = payload.get(key, 0)
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError(f"Validation Failed: {key} must be a non-negative integer.")
        return value

    @staticmethod
    def _provenance_ids(payload: Mapping[str, Any]) -> Set[str]:
        ids = payload.get("provenance_ids")
        if not isinstance(ids, list) or not ids:
            raise ValueError(
                "Validation Failed: All claims must anchor to Notus record IDs."
            )

        normalized = set()
        for record_id in ids:
            if isinstance(record_id, bool) or not isinstance(record_id, (str, int)):
                raise ValueError("Validation Failed: Invalid Notus provenance record ID.")
            value = str(record_id).strip()
            if not value:
                raise ValueError("Validation Failed: Invalid Notus provenance record ID.")
            normalized.add(value)
        if len(normalized) != len(ids):
            raise ValueError("Validation Failed: Duplicate Notus provenance record IDs.")
        return normalized

    def validate_notus_provenance(self, payload: Dict[str, Any]) -> bool:
        """Validate IDs and require any supplied confidence to match evidence.

        A numeric confidence value alone cannot reveal whether it was hardcoded.
        Instead, when confidence is supplied, it must equal the deterministic
        support/(support + contradiction) ratio.
        """
        if not isinstance(payload, Mapping):
            raise TypeError("Validation Failed: Provenance payload must be a mapping.")

        provenance_ids = self._provenance_ids(payload)
        supporting = self._count(payload, "supporting_count")
        contradicting = self._count(payload, "contradicting_count")
        if supporting + contradicting > len(provenance_ids):
            raise ValueError(
                "Validation Failed: Evidence counts exceed distinct provenance records."
            )

        confidence = payload.get("confidence")
        total_evidence = supporting + contradicting
        if confidence is not None:
            if (
                isinstance(confidence, bool)
                or not isinstance(confidence, (int, float))
                or not math.isfinite(confidence)
                or not 0.0 <= confidence <= 1.0
            ):
                raise ValueError("Validation Failed: Confidence must be finite and between 0 and 1.")
            if total_evidence == 0:
                if confidence != 0:
                    raise ValueError(
                        "Validation Failed: Confidence asserted with zero evidence records."
                    )
            elif not math.isclose(
                float(confidence),
                supporting / total_evidence,
                rel_tol=0.0,
                abs_tol=1e-9,
            ):
                raise ValueError(
                    "Validation Failed: Confidence does not match the evidence ratio."
                )

        return True

    def sanitize_liquid_schema(self, schema_dict: Dict[str, Any]) -> Dict[str, Any]:
        """Return a copy with protected top-level core keys removed."""
        if not isinstance(schema_dict, dict):
            raise TypeError("Validation Failed: Liquid schema payload must be a dictionary.")

        protected = {key.casefold() for key in self.protected_core_keys}
        return {
            key: value
            for key, value in schema_dict.items()
            if not isinstance(key, str) or key.casefold() not in protected
        }

    def validate_output_stream(self, text: str) -> bool:
        """Reject output containing configured filler or hesitation phrases."""
        if not isinstance(text, str):
            raise TypeError("Validation Failed: Output stream must be text.")

        lowered = text.casefold()
        for phrase in self.banned_phrases:
            if phrase.casefold() in lowered:
                logger.error(
                    "DataChecker violation: configured phrase detected (%r).",
                    phrase,
                )
                raise ValueError(
                    f"Validation Failed: Banned phrase {phrase!r} present in output."
                )
        return True
