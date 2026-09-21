#!/usr/bin/env python3
"""Start Monday's prompted core plus light autonomous inner-life for own feelings.

Direct-call path (no sockets): prompted lobes including PerceptionLobe
(text always; hearing/vision via file or live device when available) and AttentionLobe, plus
AutonomousThinkingLoop so mood can move from inner thoughts without user text —
plus MetaCognitionLobe watching reasoning/language for uncertainty —
plus ExecutiveControlLobe setting goals, inhibiting off-goal moves, steering Attention —
not the full legacy socket stack.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from advanced_emotional_engine import EmotionalProcess
from attention_lobe import AttentionLobe
from autonomous_thinking import AutonomousThinkingLoop
from conversation import ConversationSystem
from direct_reasoning import DirectMaximumSophisticationAdapter
from language_generation import LanguageGenerator
from notus_memory_core import ActiveNotusMemorySystem
from output import OutputLobe
from novelty_lobe import NoveltyLobe
from perception import PerceptionLobe
from sensory_integration_lobe import SensoryIntegrationLobe
from meta_cognition_lobe import MetaCognitionLobe
from executive_control_lobe import ExecutiveControlLobe
from runtime_paths import runtime_dir
from thalamus import Thalamus


def create_core_systems(
    runtime_directory: Optional[str] = None,
    reasoning_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Instantiate and register prompted-path systems plus autonomous thinking.

    `runtime_directory` is retained for mutable non-Notus runtime state and tests.
    Notus itself is PostgreSQL-only and does not use a local SQLite file.

    Postgres env (ActiveNotusMemorySystem / notus_memory._connect_postgres):
      NOTUS_POSTGRES_DSN   — full DSN; if set, wins over discrete vars
      NOTUS_POSTGRES_DB    — default ``notus_memory``
      NOTUS_POSTGRES_USER  — default ``$USER`` (e.g. box)
      NOTUS_POSTGRES_PASSWORD — optional; needed for TCP auth when not trust/peer
      NOTUS_POSTGRES_HOST  — default ``localhost``
      NOTUS_POSTGRES_PORT  — default ``5432``
    Related (not read by Notus connect, but used elsewhere):
      MONDAY_RUNTIME_DIR   — runtime_paths.runtime_dir() override
    There is no DATABASE_URL / PG* wiring in the active Notus path.
    """
    directory = Path(runtime_directory) if runtime_directory else runtime_dir()
    directory.mkdir(parents=True, exist_ok=True)
    thalamus = Thalamus()
    systems: Dict[str, Any] = {
        "thalamus": thalamus,
        "perception": PerceptionLobe(thalamus=thalamus),
        "sensory_integration": SensoryIntegrationLobe(thalamus=thalamus),
        "attention": AttentionLobe(thalamus=thalamus),
        "novelty": NoveltyLobe(thalamus=thalamus),
        "conversation": ConversationSystem(thalamus=thalamus),
        "notus": ActiveNotusMemorySystem(thalamus=thalamus),
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
    }
    for name in (
        "perception",
        "sensory_integration",
        "attention",
        "novelty",
        "conversation",
        "notus",
        "emotion",
        "reasoning",
        "language",
        "output",
        "meta_cognition",
        "executive_control",
    ):
        result = thalamus.register_lobe(name, systems[name])
        if result["status"] != "success":
            raise RuntimeError(f"Could not register {name}: {result.get('message')}")

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
        "language",
        "executive_control",
        "meta_cognition",
        "reasoning",
        "emotion",
        "notus",
        "conversation",
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
