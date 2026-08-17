#!/usr/bin/env python3
"""Start Monday's direct-call prompted core without sockets or background loops."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from advanced_emotional_engine import EmotionalProcess
from conversation import ConversationSystem
from direct_reasoning import DirectMaximumSophisticationAdapter
from language_generation import LanguageGenerator
from direct_notus import DirectNotusProcess
from learning_system import LearningSystem
from output import OutputLobe
from runtime_paths import runtime_dir
from thalamus import Thalamus


def create_core_systems(
    runtime_directory: Optional[str] = None,
    reasoning_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Instantiate and register only the six prompted-path systems.

    `runtime_directory` is intended for embedding and tests.  It defaults to
    the private directory selected by ``MONDAY_RUNTIME_DIR``.
    """
    directory = Path(runtime_directory) if runtime_directory else runtime_dir()
    directory.mkdir(parents=True, exist_ok=True)
    learning = LearningSystem(storage_path=str(directory / "learning_memory.sqlite3"))
    thalamus = Thalamus(learning_system=learning)
    systems: Dict[str, Any] = {
        "thalamus": thalamus,
        "learning": learning,
        "conversation": ConversationSystem(thalamus=thalamus),
        "notus": DirectNotusProcess(
            storage_path=str(directory / "notus_memory.sqlite3"), thalamus=thalamus
        ),
        "emotion": EmotionalProcess(
            state_file=str(directory / "emotional_state.json"), thalamus=thalamus
        ),
        "reasoning": DirectMaximumSophisticationAdapter(
            thalamus=thalamus,
            **({"reasoner_factory": reasoning_factory} if reasoning_factory else {}),
        ),
        "language": LanguageGenerator(thalamus=thalamus),
        "output": OutputLobe(thalamus=thalamus, enable_tts=False),
    }
    for name in ("conversation", "notus", "emotion", "reasoning", "language", "output"):
        result = thalamus.register_lobe(name, systems[name])
        if result["status"] != "success":
            raise RuntimeError(f"Could not register {name}: {result.get('message')}")
    return systems


def shutdown_core_systems(systems: Dict[str, Any]) -> None:
    for name in ("output", "language", "reasoning", "emotion", "notus", "conversation", "learning"):
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
