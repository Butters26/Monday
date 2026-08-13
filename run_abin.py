#!/usr/bin/env python3
"""Start Monday's direct-call prompted core without sockets or background loops."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from advanced_emotional_engine import EmotionalProcess
from conversation import ConversationSystem
from language_generation import LanguageGenerator
from notus import NotusProcess
from output import OutputLobe
from reasoning import MaximumSophisticationReasoning
from runtime_paths import runtime_dir
from thalamus import Thalamus


def create_core_systems(runtime_directory: Optional[str] = None) -> Dict[str, Any]:
    """Instantiate and register only the six prompted-path systems.

    `runtime_directory` is intended for embedding and tests.  It defaults to
    the private directory selected by ``MONDAY_RUNTIME_DIR``.
    """
    directory = Path(runtime_directory) if runtime_directory else runtime_dir()
    directory.mkdir(parents=True, exist_ok=True)
    thalamus = Thalamus()
    systems: Dict[str, Any] = {
        "thalamus": thalamus,
        "conversation": ConversationSystem(thalamus=thalamus),
        "notus": NotusProcess(
            storage_path=str(directory / "notus_memory.sqlite3"), thalamus=thalamus
        ),
        "emotion": EmotionalProcess(
            state_file=str(directory / "emotional_state.json"), thalamus=thalamus
        ),
        "reasoning": MaximumSophisticationReasoning(thalamus=thalamus),
        "language": LanguageGenerator(thalamus=thalamus),
        "output": OutputLobe(thalamus=thalamus, enable_tts=False),
    }
    for name in ("conversation", "notus", "emotion", "reasoning", "language", "output"):
        result = thalamus.register_lobe(name, systems[name])
        if result["status"] != "success":
            raise RuntimeError(f"Could not register {name}: {result.get('message')}")
    return systems


def shutdown_core_systems(systems: Dict[str, Any]) -> None:
    for name in ("output", "language", "reasoning", "emotion", "notus", "conversation"):
        shutdown = getattr(systems.get(name), "shutdown", None)
        if callable(shutdown):
            shutdown()
    systems["thalamus"].shutdown()


def main() -> int:
    systems = create_core_systems()
    print("Monday direct-call core ready:", ", ".join(systems["thalamus"].lobe_handlers))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
