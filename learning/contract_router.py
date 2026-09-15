"""Contract-driven lesson routing.

The router no longer guesses from a global keyword dictionary. It first checks
lobe learning contracts, then asks each candidate lobe whether it can actually
interpret the lesson. Ambiguous lessons fail closed instead of being sprayed
across unrelated lobes.
"""

from __future__ import annotations

from types import MethodType
from typing import Any, Dict, List


def _explicit_targets(payload: Dict[str, Any]) -> List[str]:
    raw = payload.get("target_lobes", payload.get("targets"))
    one = payload.get("target_lobe")
    if isinstance(one, str) and one.strip():
        raw = [one.strip()]
    if isinstance(raw, str):
        raw = [raw]
    if not isinstance(raw, list):
        return []
    result: List[str] = []
    for item in raw:
        if isinstance(item, str) and item.strip() and item.strip() not in result:
            result.append(item.strip())
    return result


def install_contract_router(thalamus: Any) -> None:
    """Replace global keyword routing with lobe-owned relevance decisions."""

    def _teach_target_decision(
        self: Any,
        lesson_text: str,
        lesson_type: str,
        record: Dict[str, Any],
        payload: Dict[str, Any],
    ) -> Dict[str, Any]:
        candidates = self._learning_targets_for_record(lesson_type, record)
        candidate_set = set(candidates)
        explicit = _explicit_targets(payload)
        requested = explicit if explicit else candidates
        targeted_internal: List[Dict[str, Any]] = []
        rejected: List[Dict[str, Any]] = []

        with self.lobe_handlers_lock:
            handlers = dict(self.lobe_handlers)

        for lobe_name in requested:
            if lobe_name not in candidate_set:
                rejected.append(
                    {"lobe": lobe_name, "reason": "contract_no_capability_match"}
                )
                continue

            if explicit:
                targeted_internal.append(
                    {
                        "lobe": lobe_name,
                        "reasons": ["explicit_target", "contract_capability_match"],
                        "_score": 1.0,
                    }
                )
                continue

            handler = handlers.get(lobe_name)
            assessor = getattr(handler, "assess_learning_relevance", None)
            if not callable(assessor):
                rejected.append(
                    {"lobe": lobe_name, "reason": "lobe_has_no_relevance_assessor"}
                )
                continue
            try:
                assessment = assessor(lesson_text, lesson_type, dict(record))
            except Exception as exc:
                rejected.append(
                    {
                        "lobe": lobe_name,
                        "reason": "relevance_assessment_error",
                        "message": str(exc),
                    }
                )
                continue
            if not isinstance(assessment, dict):
                rejected.append(
                    {"lobe": lobe_name, "reason": "invalid_relevance_assessment"}
                )
                continue

            accepted = bool(assessment.get("accept", False))
            try:
                score = float(assessment.get("score", 0.0))
            except (TypeError, ValueError):
                score = 0.0
            reasons = assessment.get("reasons", [])
            reasons = [
                reason for reason in reasons if isinstance(reason, str) and reason
            ] if isinstance(reasons, list) else []

            if accepted and score >= 0.65:
                targeted_internal.append(
                    {
                        "lobe": lobe_name,
                        "reasons": reasons or ["lobe_relevance_accept"],
                        "_score": score,
                    }
                )
            else:
                rejected.append(
                    {
                        "lobe": lobe_name,
                        "reason": "lobe_rejected_lesson",
                        "relevance_score": score,
                        "assessment_reasons": reasons,
                    }
                )

        if not targeted_internal:
            return {
                "status": "error",
                "routing_condition": "unresolved_target",
                "targets": [],
                "targeted": [],
                "rejected": rejected
                or [{"lobe": lobe, "reason": "unresolved_target"} for lobe in requested],
            }

        targeted_internal.sort(
            key=lambda item: float(item.get("_score", 0.0)), reverse=True
        )
        # Keep routing diagnostics stable for callers/tests; score is only an
        # internal ordering detail, not part of the public target contract.
        targeted = [
            {"lobe": entry["lobe"], "reasons": list(entry.get("reasons", []))}
            for entry in targeted_internal
        ]
        return {
            "status": "success",
            "routing_condition": "resolved_by_lobe_relevance",
            "targets": [entry["lobe"] for entry in targeted],
            "targeted": targeted,
            "rejected": rejected,
        }

    thalamus._teach_target_decision = MethodType(_teach_target_decision, thalamus)
