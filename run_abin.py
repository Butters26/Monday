#!/usr/bin/env python3
"""Start Monday's prompted core plus light autonomous inner-life for own feelings.

Direct-call path (no sockets): prompted lobes including PerceptionLobe
(text always; hearing/vision via file or live device when available) and AttentionLobe, plus
AutonomousThinkingLoop so mood can move from inner thoughts without user text —
plus MetaCognitionLobe watching reasoning/language for uncertainty —
plus ExecutiveControlLobe setting goals, inhibiting off-goal moves, steering Attention —
plus AdvancedPatternRecognition discovering patterns for Reasoning via pattern_result —
plus SocialContextLobe tracking social cues/stance across turns for Language —
plus MotorActionLobe planning/queuing action envelopes when Monday should do
something beyond talk (honest no_actuator status; no fake limbs) —
plus VoiceLobe synthesizing speech / voice envelopes from Output text
(honest synthesized/play_unavailable; no fake "she spoke") —
plus AutonomousSpeechSystem as social WHEN/WHETHER filter for speak-worthy
asides (does not invent wording or audio) —
plus SharedRepresentationSystem as common semantic substrate (stable concept IDs) —
plus MetaAwareness tracking process / dual-stream mode (wandering vs focused;
distinct from MetaCognition epistemic watching). ContinuousThoughtGenerator and
ControlledThinking stay in-tree as optional/unwired toys — NOT attached on the
live path (no mock *_fed stamps) — not the full legacy socket stack.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Dict, Optional, Tuple

from advanced_emotional_engine import EmotionalProcess
from attention_lobe import AttentionLobe
from autonomous_thinking import AutonomousThinkingLoop
from autonomous_speech import AutonomousSpeechSystem
from conversation import ConversationSystem
from direct_reasoning import DirectMaximumSophisticationAdapter
from language_generation import LanguageGenerator
from notus_memory_core import ActiveNotusMemorySystem
from direct_notus import DirectNotusProcess
from output import OutputLobe
from novelty_lobe import NoveltyLobe
from pattern_recognition import AdvancedPatternRecognition
from perception import PerceptionLobe
from sensory_integration_lobe import SensoryIntegrationLobe
from meta_cognition_lobe import MetaCognitionLobe
from executive_control_lobe import ExecutiveControlLobe
from social_context_lobe import SocialContextLobe
from motor_action_lobe import MotorActionLobe
from voice_lobe import VoiceLobe
from meta_awareness import MetaAwareness
from shared_representation import SharedRepresentationSystem
from runtime_paths import runtime_dir
from thalamus import Thalamus

# Canonical DirectNotus file when PostgreSQL is unavailable.
# Intentionally independent of MONDAY_RUNTIME_DIR / monday-chat sock dir so
# run_abin REPL and _monday_chat_daemon share one memory identity (WANT-GAP 8).
_SHARED_DIRECT_NOTUS_NAME = "notus_memory.sqlite3"


def shared_direct_notus_path() -> Path:
    """Return the one SQLite path used when Postgres is down.

    Override with ``MONDAY_NOTUS_SQLITE`` (absolute/expanded path). Default is
    ``~/.local/state/monday/notus_memory.sqlite3`` — never under monday-chat.
    Chat keeps sock/pid under ``~/.local/state/monday-chat``; memory is shared.
    """
    configured = os.environ.get("MONDAY_NOTUS_SQLITE")
    if configured:
        path = Path(configured).expanduser().resolve()
    else:
        path = (
            Path.home() / ".local" / "state" / "monday" / _SHARED_DIRECT_NOTUS_NAME
        ).resolve()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def describe_notus_identity(notus: Any) -> Dict[str, Any]:
    """Honest live-store description for chat boot logs / proofs."""
    identity = getattr(notus, "notus_identity", None)
    if isinstance(identity, dict) and identity:
        return dict(identity)
    storage = getattr(notus, "storage_path", None)
    if storage:
        return {
            "backend": "sqlite",
            "role": "injected",
            "sqlite_path": str(storage),
            "note": "Custom notus_factory (tests / explicit inject)",
        }
    return {
        "backend": type(notus).__name__,
        "role": "unknown",
        "sqlite_path": None,
        "note": "No notus_identity attached",
    }


def open_primary_notus(*, thalamus: Any) -> Any:
    """Open the single talk memory backend (WANT-GAP 8).

    Prefer PostgreSQL ``ActiveNotusMemorySystem`` (same DSN as run_abin default).
    If Postgres cannot connect (or psycopg2 missing), use ``DirectNotusProcess``
    at ``shared_direct_notus_path()`` — one file for REPL and chat daemon.

    Mid-turn Notus store/query failures still use ``Thalamus.notus_fallback``
    (Issue #11). This only chooses the durable backend at boot.
    """
    connect_errors: Tuple[type, ...]
    try:
        import psycopg2  # type: ignore

        connect_errors = (psycopg2.Error, ConnectionError, OSError, TimeoutError)
    except ImportError:
        psycopg2 = None  # type: ignore
        connect_errors = (ConnectionError, OSError, TimeoutError, ImportError)

    try:
        notus = ActiveNotusMemorySystem(thalamus=thalamus)
    except connect_errors as exc:
        sqlite_path = shared_direct_notus_path()
        notus = DirectNotusProcess(storage_path=str(sqlite_path), thalamus=thalamus)
        notus.notus_identity = {
            "backend": "sqlite",
            "role": "shared_direct_fallback",
            "sqlite_path": str(sqlite_path),
            "postgres_error": f"{type(exc).__name__}: {exc}".split("\n")[0][:240],
            "note": (
                "Postgres unavailable; DirectNotus at shared_direct_notus_path() "
                "— same file for create_core_systems / run_abin REPL and chat daemon"
            ),
        }
        return notus
    except Exception:
        # Non-connectivity failure (schema, etc.) — do not hide behind SQLite.
        raise

    notus.notus_identity = {
        "backend": "postgresql",
        "role": "primary",
        "sqlite_path": None,
        "note": "ActiveNotusMemorySystem — shared via NOTUS_POSTGRES_* / NOTUS_POSTGRES_DSN",
    }
    return notus


def create_core_systems(
    runtime_directory: Optional[str] = None,
    reasoning_factory: Optional[Any] = None,
    notus_factory: Optional[Any] = None,
    enable_autonomous: bool = True,
) -> Dict[str, Any]:
    """Instantiate and register prompted-path systems plus autonomous thinking.

    `runtime_directory` is retained for mutable non-Notus runtime state and tests
    (emotion JSON, shared_representation, etc.). It does **not** choose the Notus
    identity file when ``notus_factory`` is omitted.

    When ``notus_factory`` is omitted, ``open_primary_notus`` selects one mind:
      1. PostgreSQL ``ActiveNotusMemorySystem`` when reachable
      2. else ``DirectNotusProcess`` at ``shared_direct_notus_path()``
         (default ``~/.local/state/monday/notus_memory.sqlite3``, override
         ``MONDAY_NOTUS_SQLITE``) — shared by REPL and chat daemon
    Tests may still inject SQLite Notus via ``notus_factory`` (Postgres-free CI).

    Postgres env (ActiveNotusMemorySystem / notus_memory._connect_postgres):
      NOTUS_POSTGRES_DSN   — full DSN; if set, wins over discrete vars
      NOTUS_POSTGRES_DB    — default ``notus_memory``
      NOTUS_POSTGRES_USER  — default ``$USER`` (e.g. box)
      NOTUS_POSTGRES_PASSWORD — optional; needed for TCP auth when not trust/peer
      NOTUS_POSTGRES_HOST  — default ``localhost``
      NOTUS_POSTGRES_PORT  — default ``5432``
    Related:
      MONDAY_RUNTIME_DIR   — runtime_paths.runtime_dir() for non-Notus state
      MONDAY_NOTUS_SQLITE  — DirectNotus identity path when Postgres is down
    There is no DATABASE_URL / PG* wiring in the active Notus path.

    ``enable_autonomous=False`` skips registering/starting AutonomousThinkingLoop
    (socket-free, loop-free acceptance tests).
    """
    directory = Path(runtime_directory) if runtime_directory else runtime_dir()
    directory.mkdir(parents=True, exist_ok=True)
    thalamus = Thalamus()
    if notus_factory is None:
        notus = open_primary_notus(thalamus=thalamus)
    else:
        notus = notus_factory(thalamus=thalamus, runtime_directory=str(directory))
        if not getattr(notus, "notus_identity", None):
            notus.notus_identity = describe_notus_identity(notus)
    systems: Dict[str, Any] = {
        "thalamus": thalamus,
        # Honest live-store stamp (chat daemon / proofs read this).
        "notus_identity": describe_notus_identity(notus),
        "perception": PerceptionLobe(thalamus=thalamus),
        "sensory_integration": SensoryIntegrationLobe(thalamus=thalamus),
        "attention": AttentionLobe(thalamus=thalamus),
        "novelty": NoveltyLobe(thalamus=thalamus),
        "pattern": AdvancedPatternRecognition(thalamus=thalamus),
        "conversation": ConversationSystem(thalamus=thalamus),
        "notus": notus,
        "emotion": EmotionalProcess(
            state_file=str(directory / "emotional_state.json"), thalamus=thalamus
        ),
        "reasoning": DirectMaximumSophisticationAdapter(
            thalamus=thalamus,
            **({"reasoner_factory": reasoning_factory} if reasoning_factory else {}),
        ),
        "language": LanguageGenerator(thalamus=thalamus),
        "output": OutputLobe(thalamus=thalamus, enable_tts=False),
        "meta_cognition": MetaCognitionLobe(thalamus=thalamus),
        "executive_control": ExecutiveControlLobe(thalamus=thalamus),
        "social_context": SocialContextLobe(thalamus=thalamus),
        "motor_action": MotorActionLobe(thalamus=thalamus),
        "voice": VoiceLobe(thalamus=thalamus),
        "speech": AutonomousSpeechSystem(thalamus=thalamus),
        "meta_awareness": MetaAwareness(thalamus=thalamus),
        "shared_representation": SharedRepresentationSystem(
            thalamus=thalamus,
            store_path=str(directory / "shared_representation.json"),
        ),
    }
    for name in (
        "perception",
        "sensory_integration",
        "attention",
        "novelty",
        "pattern",
        "conversation",
        "notus",
        "emotion",
        "reasoning",
        "language",
        "output",
        "meta_cognition",
        "executive_control",
        "social_context",
        "motor_action",
        "voice",
        "speech",
        "meta_awareness",
        "shared_representation",
    ):
        result = thalamus.register_lobe(name, systems[name])
        if result["status"] != "success":
            raise RuntimeError(f"Could not register {name}: {result.get('message')}")

    # Dual-stream generators NOT attached live: ContinuousThoughtGenerator and
    # ControlledThinking are mock/toy modules. MetaAwareness still tracks mode
    # (wandering/focused) from real user turns / asides without feeding toys.
    # dual_stream_thinking.py stays unwired (Anthropic-only demo).
    # Optional: callers may still systems["meta_awareness"].set_*_system(...) by hand.

    if enable_autonomous:
        autonomous = AutonomousThinkingLoop(thalamus=thalamus)
        result = thalamus.register_lobe("autonomous", autonomous)
        if result["status"] != "success":
            raise RuntimeError(f"Could not register autonomous: {result.get('message')}")
        systems["autonomous"] = autonomous
        autonomous.start_background()
    return systems


def shutdown_core_systems(systems: Dict[str, Any]) -> None:
    for name in (
        "autonomous",
        "output",
        "voice",
        "speech",
        "meta_awareness",
        "shared_representation",
        "language",
        "motor_action",
        "social_context",
        "executive_control",
        "meta_cognition",
        "reasoning",
        "emotion",
        "notus",
        "conversation",
        "pattern",
        "novelty",
        "attention",
        "sensory_integration",
        "perception",
    ):
        shutdown = getattr(systems.get(name), "shutdown", None)
        if callable(shutdown):
            shutdown()
    systems["thalamus"].shutdown()


def main() -> int:
    systems = create_core_systems()
    print("Monday direct-call core ready. Type a message, or press Ctrl-D to exit.")
    try:
        while True:
            try:
                user_input = input("> ")
            except EOFError:
                print()
                break
            if user_input.strip():
                print(systems["thalamus"].process_user_input(user_input))
    except KeyboardInterrupt:
        print()
    finally:
        shutdown_core_systems(systems)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
