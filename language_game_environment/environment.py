"""Game environment shell for Mercy's Language lobe.

This is deliberately NOT the game.

It provides:
- isolated Language contestants,
- access to Language's own current comprehension/lexicon resources,
- optional assistance from registered lobe helpers,
- hard ordering/ownership checks,
- assistance and final-submission tracing,
- no grader, scoring, lesson, mutation, selection, or evolution logic.

The future game owns the problems and grading. This environment only enforces
how a Language contestant is allowed to work on them.
"""

from __future__ import annotations

import json
import os
import re
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

from language_comprehension import LanguageComprehensionEngine
from lexicon.oewn_offline import lookup_senses

from .rules import (
    ALLOWED_ASSISTANCE_FIELDS,
    DEFAULT_RULES,
    FORBIDDEN_ASSISTANCE_FIELDS,
    FORBIDDEN_PUBLIC_PROBLEM_FIELDS,
    EnvironmentRules,
)


class GameRuleViolation(RuntimeError):
    """Raised when a contestant/helper tries to cross an environment rule."""


@dataclass(frozen=True)
class HelpRequest:
    """Sanitized request a helper lobe is allowed to see.

    It intentionally contains no grader, answer, score, hidden-test, environment,
    or helper-registry handle. That prevents the normal path from chaining help
    or peeking at grading state.
    """

    contestant_id: str
    problem_id: str
    helper_lobe: str
    request: str
    visible_context: Mapping[str, Any]
    independent_candidate: Any


@dataclass(frozen=True)
class AssistancePacket:
    """Allowed shape of a helper response.

    A helper may return supporting observations/context only. It may not return
    answer-shaped fields such as `answer`, `selected_sense`, or `sense_id`.
    """

    source_lobe: str
    observations: Tuple[str, ...] = ()
    context: Mapping[str, Any] = field(default_factory=dict)
    confidence: Optional[float] = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class FinalSubmission:
    """Language-owned final submission passed outward to a future game/grader."""

    contestant_id: str
    problem_id: str
    answer: Any
    assisted: bool
    assistance_count: int


@dataclass
class _ProblemState:
    visible_context: Dict[str, Any]
    own_resource_events: List[Dict[str, Any]] = field(default_factory=list)
    independent_attempt: Any = None
    independent_attempt_recorded: bool = False
    assistance: List[AssistancePacket] = field(default_factory=list)
    final_submission: Optional[FinalSubmission] = None


HelperCallable = Callable[[HelpRequest], Mapping[str, Any]]
LanguageFactory = Callable[[], LanguageComprehensionEngine]


_RESERVED_HELPER_NAMES = frozenset(
    {
        "language",
        "grader",
        "game",
        "environment",
        "scorer",
        "judge",
    }
)


def _contains_forbidden_key(value: Any, forbidden: frozenset[str]) -> Optional[str]:
    """Return the first forbidden mapping key found recursively, if any."""

    if isinstance(value, Mapping):
        for key, child in value.items():
            normalized = str(key).strip().lower()
            if normalized in forbidden:
                return normalized
            found = _contains_forbidden_key(child, forbidden)
            if found:
                return found
    elif isinstance(value, (list, tuple, set)):
        for child in value:
            found = _contains_forbidden_key(child, forbidden)
            if found:
                return found
    return None


def _safe_component(value: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_.-]+", "_", str(value or "").strip())
    return clean[:120] or "unnamed"


class LanguageContestantSession:
    """One isolated Language contestant inside the environment.

    The contestant owns one LanguageComprehensionEngine instance and one private
    runtime directory. The session is the only object with `submit_final`.
    Helper callables never receive this object.
    """

    def __init__(
        self,
        *,
        environment: "LanguageGameEnvironment",
        contestant_id: str,
        state_dir: Path,
        language: LanguageComprehensionEngine,
    ) -> None:
        self._environment = environment
        self.contestant_id = contestant_id
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.language = language
        self._problems: Dict[str, _ProblemState] = {}
        self._trace_path = self.state_dir / "trace.jsonl"

    @property
    def rules(self) -> EnvironmentRules:
        """Read-only frozen rules. No setter exists."""

        return self._environment.rules

    def _trace(self, event: str, payload: Mapping[str, Any]) -> None:
        record = {
            "event": event,
            "contestant_id": self.contestant_id,
            **dict(payload),
        }
        with self._trace_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def _state(self, problem_id: str) -> _ProblemState:
        key = str(problem_id or "").strip()
        if not key or key not in self._problems:
            raise GameRuleViolation("Problem must be started before Language can act on it")
        return self._problems[key]

    def start_problem(
        self,
        problem_id: str,
        *,
        visible_context: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Open a problem with contestant-visible context only.

        This method does not define a problem or answer. A future game supplies
        the context. Known grading/solution fields are rejected here.
        """

        key = str(problem_id or "").strip()
        if not key:
            raise ValueError("problem_id is required")
        if key in self._problems:
            raise GameRuleViolation(f"Problem already started: {key}")

        context = dict(visible_context or {})
        leaked = _contains_forbidden_key(context, FORBIDDEN_PUBLIC_PROBLEM_FIELDS)
        if leaked:
            raise GameRuleViolation(
                f"Public problem context contains reserved grading/answer field: {leaked}"
            )

        self._problems[key] = _ProblemState(visible_context=context)
        self._trace("problem_started", {"problem_id": key, "visible_context": context})

    def lookup_own_lexicon(
        self,
        problem_id: str,
        surface: str,
        *,
        pos: Optional[str] = None,
        max_senses: int = 8,
    ) -> List[Dict[str, Any]]:
        """Use Language's own offline OEWN resource and record that self-work.

        The environment does not provide a definition. This calls the same
        Language-owned OEWN lookup resource Mercy already has.
        """

        state = self._state(problem_id)
        senses = lookup_senses(surface, pos=pos, max_senses=max_senses)
        event = {
            "resource": "language_oewn_lexicon",
            "surface": str(surface),
            "pos": pos,
            "result_count": len(senses),
        }
        state.own_resource_events.append(event)
        self._trace("own_resource_used", {"problem_id": problem_id, **event})
        return senses

    def analyze_with_own_language(self, problem_id: str, text: str) -> Dict[str, Any]:
        """Run this contestant's own current Language comprehension machinery."""

        state = self._state(problem_id)
        packet = self.language.analyze(text)
        event = {
            "resource": "language_comprehension_engine",
            "text": str(text),
        }
        state.own_resource_events.append(event)
        self._trace("own_resource_used", {"problem_id": problem_id, **event})
        return packet

    def mark_own_resource_use(
        self,
        problem_id: str,
        *,
        resource: str,
        details: Optional[Mapping[str, Any]] = None,
    ) -> None:
        """Record another Language-owned resource used by a future learner.

        This is intentionally generic so later Language learning internals can be
        added without changing the environment's rules.
        """

        state = self._state(problem_id)
        resource_name = str(resource or "").strip()
        if not resource_name:
            raise ValueError("resource is required")
        event = {
            "resource": resource_name,
            "details": dict(details or {}),
        }
        state.own_resource_events.append(event)
        self._trace("own_resource_used", {"problem_id": problem_id, **event})

    def record_independent_attempt(
        self,
        problem_id: str,
        candidate: Any,
    ) -> None:
        """Record Language's own candidate before any helper may be consulted."""

        state = self._state(problem_id)
        if state.final_submission is not None:
            raise GameRuleViolation("Cannot change an attempt after final submission")
        if not state.own_resource_events:
            raise GameRuleViolation(
                "Language must use/inspect its own resources before recording an independent attempt"
            )
        if state.assistance:
            raise GameRuleViolation(
                "Independent attempt must be recorded before any assistance is received"
            )
        state.independent_attempt = candidate
        state.independent_attempt_recorded = True
        self._trace(
            "independent_attempt",
            {"problem_id": problem_id, "candidate": candidate},
        )

    def request_assistance(
        self,
        problem_id: str,
        helper_lobe: str,
        request: str,
    ) -> AssistancePacket:
        """Ask one registered helper after Language has tried on its own."""

        state = self._state(problem_id)
        if state.final_submission is not None:
            raise GameRuleViolation("Cannot request assistance after final submission")
        if not state.own_resource_events:
            raise GameRuleViolation("Language must use its own resources before asking for help")
        if not state.independent_attempt_recorded:
            raise GameRuleViolation("Language must make an independent attempt before asking for help")

        helper_name = str(helper_lobe or "").strip().lower()
        help_request = HelpRequest(
            contestant_id=self.contestant_id,
            problem_id=str(problem_id),
            helper_lobe=helper_name,
            request=str(request or "").strip(),
            visible_context=dict(state.visible_context),
            independent_candidate=state.independent_attempt,
        )
        packet = self._environment._request_assistance(help_request)
        state.assistance.append(packet)
        self._trace(
            "assistance",
            {
                "problem_id": problem_id,
                "helper_lobe": helper_name,
                "request": help_request.request,
                "response": {
                    "source_lobe": packet.source_lobe,
                    "observations": list(packet.observations),
                    "context": dict(packet.context),
                    "confidence": packet.confidence,
                    "metadata": dict(packet.metadata),
                },
            },
        )
        return packet

    def submit_final(self, problem_id: str, answer: Any) -> FinalSubmission:
        """Submit Language's final decision to the future game/grader boundary."""

        state = self._state(problem_id)
        if state.final_submission is not None:
            raise GameRuleViolation("Final answer already submitted")
        if not state.own_resource_events:
            raise GameRuleViolation("Language cannot submit without first using its own resources")
        if not state.independent_attempt_recorded:
            raise GameRuleViolation("Language cannot submit without an independent attempt")

        submission = FinalSubmission(
            contestant_id=self.contestant_id,
            problem_id=str(problem_id),
            answer=answer,
            assisted=bool(state.assistance),
            assistance_count=len(state.assistance),
        )
        state.final_submission = submission
        self._trace(
            "final_submission",
            {
                "problem_id": problem_id,
                "answer": answer,
                "assisted": submission.assisted,
                "assistance_count": submission.assistance_count,
            },
        )
        return submission

    def assistance_trace(self, problem_id: str) -> Tuple[AssistancePacket, ...]:
        """Read-only snapshot of help used on one problem."""

        return tuple(self._state(problem_id).assistance)


class LanguageGameEnvironment:
    """Container for isolated Language contestants and permitted lobe helpers.

    This class deliberately has no `grade`, `score`, `reward`, `mutate`,
    `select`, `breed`, or `evolve` method. Those belong to the game the user
    designs later.
    """

    def __init__(
        self,
        *,
        runtime_root: Optional[os.PathLike[str] | str] = None,
        language_factory: Optional[LanguageFactory] = None,
        rules: EnvironmentRules = DEFAULT_RULES,
    ) -> None:
        self.rules = rules
        if runtime_root is None:
            runtime_root = os.environ.get(
                "MERCY_LANGUAGE_GAME_RUNTIME",
                str(Path.home() / ".local" / "state" / "mercy" / "language_game"),
            )
        self.runtime_root = Path(runtime_root).expanduser().resolve()
        self.runtime_root.mkdir(parents=True, exist_ok=True)
        self._contestant_root = self.runtime_root / "contestants"
        self._contestant_root.mkdir(parents=True, exist_ok=True)
        self._language_factory: LanguageFactory = language_factory or LanguageComprehensionEngine
        self._helpers: Dict[str, HelperCallable] = {}

    def register_helper(self, lobe_name: str, helper: HelperCallable) -> None:
        """Register a lobe-scoped assistance adapter.

        The helper receives only HelpRequest. It never receives this environment,
        a contestant session, grader state, or another helper handle.
        """

        name = str(lobe_name or "").strip().lower()
        if not name:
            raise ValueError("lobe_name is required")
        if name in _RESERVED_HELPER_NAMES:
            raise GameRuleViolation(f"Reserved helper name cannot be registered: {name}")
        if not callable(helper):
            raise TypeError("helper must be callable")
        self._helpers[name] = helper

    def create_contestant(self, contestant_id: Optional[str] = None) -> LanguageContestantSession:
        """Create one Language copy with contestant-specific state."""

        cid = str(contestant_id or uuid.uuid4()).strip()
        if not cid:
            raise ValueError("contestant_id is required")
        safe_id = _safe_component(cid)
        state_dir = self._contestant_root / safe_id
        if state_dir.exists() and any(state_dir.iterdir()):
            raise GameRuleViolation(f"Contestant state already exists: {cid}")
        language = self._language_factory()
        return LanguageContestantSession(
            environment=self,
            contestant_id=cid,
            state_dir=state_dir,
            language=language,
        )

    def create_population(self, count: int) -> Tuple[LanguageContestantSession, ...]:
        """Create multiple independent Language copies; no game is run."""

        total = int(count)
        if total < 1:
            raise ValueError("count must be at least 1")
        return tuple(self.create_contestant() for _ in range(total))

    def _request_assistance(self, request: HelpRequest) -> AssistancePacket:
        """Enforce helper response shape and block answer/grader-shaped data."""

        name = request.helper_lobe
        helper = self._helpers.get(name)
        if helper is None:
            raise GameRuleViolation(f"Helper lobe is not registered: {name}")

        raw = helper(request)
        if not isinstance(raw, Mapping):
            raise GameRuleViolation(
                "Helper must return a structured assistance mapping, not direct prose/answer"
            )

        extra = {str(key) for key in raw.keys()} - set(ALLOWED_ASSISTANCE_FIELDS)
        if extra:
            raise GameRuleViolation(
                "Helper response contains fields outside the assistance contract: "
                + ", ".join(sorted(extra))
            )

        forbidden = _contains_forbidden_key(raw, FORBIDDEN_ASSISTANCE_FIELDS)
        if forbidden:
            raise GameRuleViolation(
                f"Helper response contains answer/grader-shaped field: {forbidden}"
            )

        observations_raw = raw.get("observations") or ()
        if isinstance(observations_raw, str):
            observations = (observations_raw,)
        else:
            observations = tuple(str(item) for item in observations_raw)

        context = raw.get("context") or {}
        metadata = raw.get("metadata") or {}
        if not isinstance(context, Mapping) or not isinstance(metadata, Mapping):
            raise GameRuleViolation("Helper context and metadata must be mappings")

        confidence_raw = raw.get("confidence")
        confidence: Optional[float]
        if confidence_raw is None:
            confidence = None
        else:
            confidence = float(confidence_raw)
            if not 0.0 <= confidence <= 1.0:
                raise GameRuleViolation("Helper confidence must be between 0 and 1")

        return AssistancePacket(
            source_lobe=name,
            observations=observations,
            context=dict(context),
            confidence=confidence,
            metadata=dict(metadata),
        )
