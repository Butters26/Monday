"""
MetaCognitionLobe — Monday watching her own thinking on the live path.

Observes reasoning/language outputs for empty grounding, uncertainty markers,
surface contradiction, and overconfidence without evidence. Emits control
signals Thalamus can apply (force grounded refusal, flag uncertainty to
Language/Output, nudge Attention). Does not invent facts; does not rebuild
Reasoning / Language / Emotion.

Honest limits: surface heuristics on text + structures only. Cannot verify
external-world truth, cannot catch subtle fallacies, cannot read private
intent beyond what lobes expose.
"""

from __future__ import annotations

import re
import time
from typing import Any, Dict, List, Optional, Sequence, Tuple


GROUNDED_REFUSAL = (
    "I don't have enough grounded information for that yet. "
    "What should I know?"
)

_UNCERTAINTY_MARKERS = (
    "i do not know",
    "i don't know",
    "i'm not sure",
    "i am not sure",
    "not sure",
    "uncertain",
    "unsure",
    "no idea",
    "cannot tell",
    "can't tell",
    "unclear",
    "maybe",
    "might be",
    "possibly",
    "i wonder",
    "express_uncertainty",
)

_OVERCONFIDENT_MARKERS = (
    "definitely",
    "certainly",
    "absolutely",
    "without a doubt",
    "for sure",
    "always",
    "never",
    "guaranteed",
    "obviously",
    "clearly the answer",
)

_REFUSAL_PREFIXES = (
    "i do not have enough grounded",
    "i don't have enough grounded",
    "i am unable to formulate",
    "i'm unable to formulate",
    "i am unable to",
    "i'm unable to",
)

_EMPATHIC_OR_SOCIAL = (
    "got it",
    "hello",
    "hi ",
    "hey",
    "that sounds",
    "i hear",
    "i'm here",
    "i am here",
    "i am sitting",
    "i'm sitting",
)


class MetaCognitionLobe:
    """Monitor live thinking; emit steering signals — not print theater."""

    def __init__(self, thalamus: Any = None) -> None:
        self.thalamus = thalamus
        self.self_state: Dict[str, Any] = {}
        self.error_log: List[Any] = []
        self.last_verdict: Optional[Dict[str, Any]] = None
        self.monitor_count: int = 0
        self._history: List[Dict[str, Any]] = []

    @staticmethod
    def _text(value: Any) -> str:
        if isinstance(value, str):
            return value.strip()
        if value is None:
            return ""
        return str(value).strip()

    @classmethod
    def _low(cls, value: Any) -> str:
        return cls._text(value).lower()

    @classmethod
    def _is_refusal(cls, text: str) -> bool:
        low = cls._low(text)
        return bool(low) and any(low.startswith(p) for p in _REFUSAL_PREFIXES)

    @classmethod
    def _is_social_or_empathic(cls, text: str) -> bool:
        low = cls._low(text)
        return bool(low) and any(low.startswith(p) for p in _EMPATHIC_OR_SOCIAL)

    @classmethod
    def _has_uncertainty_markers(cls, text: str) -> bool:
        low = cls._low(text)
        return bool(low) and any(m in low for m in _UNCERTAINTY_MARKERS)

    @classmethod
    def _has_overconfident_markers(cls, text: str) -> bool:
        low = cls._low(text)
        return bool(low) and any(m in low for m in _OVERCONFIDENT_MARKERS)

    @staticmethod
    def _structure_props(structures: Any) -> List[Tuple[str, str, str]]:
        props: List[Tuple[str, str, str]] = []
        if not isinstance(structures, list):
            return props
        for item in structures:
            if isinstance(item, dict):
                subj = str(
                    item.get("subject")
                    or item.get("entity")
                    or item.get("s")
                    or ""
                ).strip().lower()
                rel = str(
                    item.get("relation")
                    or item.get("predicate")
                    or item.get("r")
                    or ""
                ).strip().lower()
                obj = str(
                    item.get("object")
                    or item.get("value")
                    or item.get("o")
                    or ""
                ).strip().lower()
                if subj or rel or obj:
                    props.append((subj, rel, obj))
            elif isinstance(item, str) and item.strip():
                props.append(("", "", item.strip().lower()))
        return props

    @classmethod
    def _surface_contradictions(
        cls, structures: Any, answer_text: str
    ) -> List[str]:
        """Catch simple subject+relation conflicts — not deep logic."""
        found: List[str] = []
        props = cls._structure_props(structures)
        by_key: Dict[Tuple[str, str], List[str]] = {}
        for subj, rel, obj in props:
            if not subj or not rel:
                continue
            key = (subj, rel)
            by_key.setdefault(key, []).append(obj)
        for (subj, rel), objs in by_key.items():
            distinct = {o for o in objs if o}
            if len(distinct) >= 2:
                found.append(
                    f"conflicting values for {subj}.{rel}: {sorted(distinct)}"
                )
        low = cls._low(answer_text)
        if low and (" is not " in low or " isn't " in low) and " is " in low:
            m_pos = re.findall(r"\b([\w'-]+)\s+is\s+([\w'-]+)", low)
            m_neg = re.findall(r"\b([\w'-]+)\s+(?:is not|isn't)\s+([\w'-]+)", low)
            for s, o in m_pos:
                for ns, no in m_neg:
                    if s == ns and o == no:
                        found.append(f"answer affirms and negates '{s} is {o}'")
        return found

    @staticmethod
    def _memory_count(memories: Any) -> int:
        if not isinstance(memories, Sequence) or isinstance(memories, (str, bytes)):
            return 0
        n = 0
        for m in memories:
            if isinstance(m, dict):
                content = m.get("content") or m.get("text") or m.get("object")
                if content:
                    n += 1
            elif isinstance(m, str) and m.strip():
                n += 1
        return n


    @staticmethod
    def _findings_have_contradiction(findings: Any) -> bool:
        for item in findings or []:
            if not isinstance(item, str):
                continue
            low = item.lower()
            if "conflicting values" in low or "affirms and negates" in low:
                return True
        return False

    def monitor_reasoning(
        self,
        *,
        user_input: str = "",
        semantic_input: Optional[Dict[str, Any]] = None,
        reasoning_answer: Any = None,
        memories: Any = None,
    ) -> Dict[str, Any]:
        """Observe reasoning envelope before Language; emit control signals."""
        semantic_input = dict(semantic_input or {})
        answer = self._text(reasoning_answer)
        if not answer:
            for key in ("answer", "conclusion"):
                answer = self._text(semantic_input.get(key))
                if answer:
                    break
        # Only dict-shaped grounded_structures count as real grounding.
        # Propositions often hold refusal prose — do not treat those as evidence.
        raw_structures = semantic_input.get("grounded_structures")
        structures: list = []
        if isinstance(raw_structures, list):
            structures = [
                item
                for item in raw_structures
                if isinstance(item, dict)
                and (
                    item.get("object")
                    or item.get("value")
                    or item.get("predicate")
                    or item.get("relation")
                    or item.get("subject")
                )
            ]
        has_structures = bool(structures)
        intent = self._text(semantic_input.get("intent")).lower()
        mem_n = self._memory_count(memories)

        try:
            confidence = float(semantic_input.get("confidence", 0.5))
        except (TypeError, ValueError):
            confidence = 0.5

        findings: List[str] = []
        signals: Dict[str, Any] = {
            "force_grounded_refusal": False,
            "flag_uncertainty": False,
            "nudge_attention": False,
            "ok_grounded": False,
        }

        is_refusal = self._is_refusal(answer)
        is_social = self._is_social_or_empathic(answer)
        empty_grounding = (not has_structures) and (not answer or is_refusal)
        uncertain = intent == "express_uncertainty" or self._has_uncertainty_markers(
            answer
        )
        if (not has_structures) and self._has_uncertainty_markers(user_input):
            uncertain = True

        overconfident = False
        if not has_structures and not is_refusal and not is_social and answer:
            if self._has_overconfident_markers(answer) or confidence >= 0.85:
                overconfident = True
                findings.append(
                    "overconfidence without grounded structures/evidence"
                )

        contradictions = self._surface_contradictions(structures, answer)
        if contradictions:
            findings.extend(contradictions)

        if empty_grounding:
            findings.append("empty_or_refusal_grounding")
            signals["flag_uncertainty"] = True
            signals["nudge_attention"] = True
        if uncertain and not has_structures:
            findings.append("uncertainty_markers")
            signals["flag_uncertainty"] = True
            signals["nudge_attention"] = True
        if overconfident:
            signals["force_grounded_refusal"] = True
            signals["flag_uncertainty"] = True
            signals["nudge_attention"] = True
        if contradictions:
            signals["flag_uncertainty"] = True
            signals["nudge_attention"] = True
            if not has_structures:
                signals["force_grounded_refusal"] = True

        if has_structures and not contradictions and not overconfident:
            signals["ok_grounded"] = True
            findings.append("grounded_structures_present")

        if signals["ok_grounded"]:
            path = "grounded"
        elif overconfident:
            path = "overconfident_ungrounded"
        elif empty_grounding or uncertain or contradictions:
            path = "uncertain_or_empty"
        else:
            path = "neutral"

        verdict = {
            "path": path,
            "findings": findings,
            "signals": signals,
            "has_structures": has_structures,
            "is_refusal": is_refusal,
            "memory_count": mem_n,
            "confidence_seen": confidence,
            "answer_preview": answer[:160],
            "limits": (
                "surface heuristics only; cannot verify external truth "
                "or deep logic"
            ),
            "observed_at": time.time(),
        }
        # Preserve conflicting grounded structures for diagnosis — do not
        # delete from Notus; Language handoff clears them in apply_to_semantic.
        if contradictions and structures:
            verdict["conflicting_structures"] = [
                dict(item) if isinstance(item, dict) else item
                for item in structures
            ]
            verdict["contradiction_blocked"] = True
        self.last_verdict = verdict
        self.monitor_count += 1
        self._history.append({"phase": "reasoning", **verdict})
        if len(self._history) > 40:
            self._history = self._history[-40:]
        return verdict

    def apply_to_semantic(
        self, semantic_input: Dict[str, Any], verdict: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Mutate a copy of semantic_input per control signals."""
        out = dict(semantic_input or {})
        signals = (verdict or {}).get("signals") or {}
        findings = list((verdict or {}).get("findings") or [])
        conflicting = (verdict or {}).get("conflicting_structures")
        if not isinstance(conflicting, list) or not conflicting:
            conflicting = None
            raw = out.get("grounded_structures")
            if (
                self._findings_have_contradiction(findings)
                and isinstance(raw, list)
                and raw
            ):
                conflicting = [
                    dict(item) if isinstance(item, dict) else item for item in raw
                ]

        meta: Dict[str, Any] = {
            "path": verdict.get("path"),
            "findings": findings,
            "signals": dict(signals),
            "limits": verdict.get("limits"),
        }
        if conflicting:
            # Diagnosis only — Notus untouched; Language must not compose either.
            meta["conflicting_structures"] = conflicting
            meta["contradiction_blocked"] = True
        out["meta_cognition"] = meta

        if signals.get("force_grounded_refusal"):
            out["grounded_structures"] = []
            out["propositions"] = [GROUNDED_REFUSAL]
            out["answer"] = GROUNDED_REFUSAL
            out["intent"] = "express_uncertainty"
            try:
                out["certainty"] = min(float(out.get("certainty") or 0.3), 0.3)
            except (TypeError, ValueError):
                out["certainty"] = 0.3
        elif signals.get("flag_uncertainty"):
            if conflicting:
                # Safe effect like force_grounded_refusal for composition, but
                # keep conflicting_structures on meta for diagnosis/logging.
                out["grounded_structures"] = []
                out["propositions"] = [GROUNDED_REFUSAL]
                out["answer"] = GROUNDED_REFUSAL
                out["intent"] = "express_uncertainty"
                # Prevent Language salvage from picking one conflicting side.
                out["memory_context"] = []
                try:
                    out["certainty"] = min(float(out.get("certainty") or 0.3), 0.3)
                except (TypeError, ValueError):
                    out["certainty"] = 0.3
                out["uncertainty_flagged"] = True
            elif not verdict.get("has_structures"):
                if not self._is_refusal(self._text(out.get("answer"))):
                    out.setdefault("intent", "express_uncertainty")
                try:
                    out["certainty"] = min(float(out.get("certainty") or 0.4), 0.4)
                except (TypeError, ValueError):
                    out["certainty"] = 0.4
                out["uncertainty_flagged"] = True
            else:
                out["uncertainty_flagged"] = True
        return out

    def monitor_language(
        self,
        *,
        sentence: str = "",
        semantic_input: Optional[Dict[str, Any]] = None,
        prior_verdict: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Second look after Language; catch invented-sounding confident prose."""
        semantic_input = semantic_input or {}
        prior = prior_verdict or self.last_verdict or {}
        text = self._text(sentence)
        findings: List[str] = list(prior.get("findings") or [])
        signals = dict((prior.get("signals") or {}))
        meta = (
            semantic_input.get("meta_cognition")
            if isinstance(semantic_input.get("meta_cognition"), dict)
            else {}
        )

        prior_empty = prior.get("path") in {
            "uncertain_or_empty",
            "overconfident_ungrounded",
        } or bool((prior.get("signals") or {}).get("flag_uncertainty"))
        has_structures = bool(prior.get("has_structures"))
        prior_contradiction = self._findings_have_contradiction(findings) or bool(
            prior.get("contradiction_blocked")
        )
        if (
            prior_empty
            and text
            and not self._is_refusal(text)
            and not self._is_social_or_empathic(text)
            and not has_structures
            and self._has_overconfident_markers(text)
        ):
            findings.append("language_overconfident_after_empty_grounding")
            signals["force_grounded_refusal"] = True
            signals["flag_uncertainty"] = True

        # Safety net: never let Language assert a side when Meta saw conflict.
        if (
            prior_contradiction
            and text
            and not self._is_refusal(text)
            and not self._is_social_or_empathic(text)
        ):
            findings.append("language_asserted_despite_contradiction")
            signals["force_grounded_refusal"] = True
            signals["flag_uncertainty"] = True

        if prior.get("path") == "grounded" and text and self._is_refusal(text):
            findings.append("language_refused_despite_grounding")

        path = prior.get("path") or "neutral"
        if signals.get("force_grounded_refusal"):
            path = "overconfident_ungrounded"
        elif signals.get("flag_uncertainty") and path == "grounded":
            path = "uncertain_or_empty"

        corrected = GROUNDED_REFUSAL if signals.get("force_grounded_refusal") else None

        conflicting = prior.get("conflicting_structures")
        if isinstance(meta, dict) and isinstance(meta.get("conflicting_structures"), list):
            conflicting = meta.get("conflicting_structures")

        verdict = {
            "path": path,
            "findings": findings,
            "signals": signals,
            "has_structures": has_structures,
            "is_refusal": self._is_refusal(text) if text else prior.get("is_refusal"),
            "sentence_preview": text[:160],
            "corrected_sentence": corrected,
            "prior_path": prior.get("path"),
            "meta_from_semantic": meta,
            "limits": prior.get("limits")
            or (
                "surface heuristics only; cannot verify external truth "
                "or deep logic"
            ),
            "observed_at": time.time(),
        }
        if isinstance(conflicting, list) and conflicting:
            verdict["conflicting_structures"] = conflicting
            verdict["contradiction_blocked"] = True
        self.last_verdict = verdict
        self.monitor_count += 1
        self._history.append({"phase": "language", **verdict})
        if len(self._history) > 40:
            self._history = self._history[-40:]
        return verdict

    def nudge_attention(self, reason: str = "meta_uncertainty") -> Dict[str, Any]:
        """Soft Attention boost for epistemic concern — no Attention rebuild."""
        if not self.thalamus:
            return {"nudged": False, "reason": "no_thalamus"}
        handlers = getattr(self.thalamus, "lobe_handlers", None) or {}
        if "attention" not in handlers:
            return {"nudged": False, "reason": "attention_offline"}
        send = getattr(self.thalamus, "send_message", None)
        if not callable(send):
            return {"nudged": False, "reason": "no_send"}
        payload = {
            "signals": [
                {
                    "id": f"meta:{reason}",
                    "text": f"meta-cognition: {reason}",
                    "source": "meta_cognition",
                    "modality": "meta",
                    "urgency": 0.7,
                }
            ]
        }
        try:
            resp = send(
                "attention",
                "update_salience",
                payload,
                source="meta_cognition",
            )
            return {
                "nudged": resp.get("status") == "success",
                "response": resp,
                "reason": reason,
            }
        except Exception as exc:
            return {"nudged": False, "reason": str(exc)}

    def assess_self(self, state: Dict[str, Any]) -> None:
        self.self_state.update(state or {})

    def detect_error(self, error: Any) -> None:
        self.error_log.append(error)
        if self.thalamus:
            try:
                handlers = getattr(self.thalamus, "lobe_handlers", None) or {}
                if "executive_control" in handlers:
                    self.thalamus.send_message(
                        "executive_control",
                        "add_task",
                        {"task": {"type": "remediate", "error": error}},
                        source="meta_cognition",
                    )
            except Exception:
                pass

    def reset(self) -> None:
        self.self_state.clear()
        self.error_log.clear()
        self.last_verdict = None
        self._history.clear()

    def get_status(self) -> Dict[str, Any]:
        return {
            "monitor_count": self.monitor_count,
            "last_path": (self.last_verdict or {}).get("path"),
            "last_findings": list((self.last_verdict or {}).get("findings") or []),
            "last_signals": dict((self.last_verdict or {}).get("signals") or {}),
            "error_log_len": len(self.error_log),
            "history_len": len(self._history),
        }

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        if "content" in message:
            content = message.get("content") or {}
        else:
            content = {
                k: v
                for k, v in message.items()
                if k not in ("type", "_message_id", "message_id", "source")
            }
        if not isinstance(content, dict):
            content = {}

        if msg_type in ("monitor_reasoning", "monitor"):
            verdict = self.monitor_reasoning(
                user_input=self._text(content.get("user_input")),
                semantic_input=content.get("semantic_input")
                if isinstance(content.get("semantic_input"), dict)
                else content,
                reasoning_answer=content.get("reasoning_answer"),
                memories=content.get("memories"),
            )
            applied = None
            if content.get("apply"):
                sem = content.get("semantic_input")
                if isinstance(sem, dict):
                    applied = self.apply_to_semantic(sem, verdict)
            if verdict.get("signals", {}).get("nudge_attention"):
                nudge = self.nudge_attention(
                    reason=verdict.get("path") or "meta_uncertainty"
                )
            else:
                nudge = {"nudged": False, "reason": "not_requested"}
            return {
                "status": "success",
                "verdict": verdict,
                "semantic_input": applied,
                "attention_nudge": nudge,
                "content": {
                    "verdict": verdict,
                    "semantic_input": applied,
                    "attention_nudge": nudge,
                },
            }

        if msg_type == "monitor_language":
            verdict = self.monitor_language(
                sentence=self._text(content.get("sentence")),
                semantic_input=content.get("semantic_input")
                if isinstance(content.get("semantic_input"), dict)
                else {},
                prior_verdict=content.get("prior_verdict")
                if isinstance(content.get("prior_verdict"), dict)
                else None,
            )
            return {
                "status": "success",
                "verdict": verdict,
                "content": {"verdict": verdict},
            }

        if msg_type == "evaluate_thought":
            thought = content.get("thought") or {}
            if not isinstance(thought, dict):
                thought = {}
            verdict = self.monitor_reasoning(
                user_input=self._text(thought.get("content")),
                semantic_input={
                    "answer": thought.get("content"),
                    "confidence": thought.get("confidence", 0.5),
                    "intent": thought.get("type"),
                    "grounded_structures": thought.get("grounded_structures"),
                },
                reasoning_answer=thought.get("content"),
                memories=thought.get("memories"),
            )
            risks = list(verdict.get("findings") or [])
            evaluation = {
                "path": verdict.get("path"),
                "risks": risks,
                "signals": verdict.get("signals"),
                "limits": verdict.get("limits"),
            }
            return {
                "status": "success",
                "evaluation": evaluation,
                "content": {"evaluation": evaluation},
            }

        if msg_type == "assess_self":
            self.assess_self(content.get("state") or {})
            return {
                "status": "success",
                "self_state": self.self_state,
                "content": {"self_state": self.self_state},
            }

        if msg_type == "detect_error":
            err = content.get("error")
            if err is None:
                return {"status": "error", "message": "Missing error"}
            self.detect_error(err)
            return {"status": "success", "message": "Error logged"}

        if msg_type == "get_errors":
            return {
                "status": "success",
                "errors": list(self.error_log),
                "content": {"errors": list(self.error_log)},
            }

        if msg_type in ("get_status", "status"):
            st = self.get_status()
            return {"status": "success", "content": st, **st}

        if msg_type == "get_last_verdict":
            return {
                "status": "success",
                "verdict": self.last_verdict,
                "content": {"verdict": self.last_verdict},
            }

        if msg_type == "reset":
            self.reset()
            return {"status": "success", "message": "MetaCognitionLobe reset"}

        if msg_type == "health":
            return {
                "status": "success",
                "content": {"healthy": True, "monitor_count": self.monitor_count},
            }

        return {
            "status": "error",
            "message": f"Unknown message type: {msg_type}",
        }
