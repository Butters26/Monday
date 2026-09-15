#!/usr/bin/env python3
"""Start Monday's direct-call prompted core without sockets or background loops."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, Optional

from direct_notus import DirectNotusProcess
from runtime_paths import runtime_dir
from thalamus import Thalamus
from learning.adaptive_lobes import (
    AdaptiveConversationSystem,
    AdaptiveEmotionProcess,
    AdaptiveLanguageGenerator,
    AdaptiveOutputLobe,
    AdaptivePatternRecognition,
    AdaptiveReasoningAdapter,
)
from learning.runtime_integration_native import install_learning_integration
from learning.hardening import install_hardened_stores


def create_core_systems(
    runtime_directory: Optional[str] = None,
    reasoning_factory: Optional[Any] = None,
) -> Dict[str, Any]:
    """Instantiate and register direct-call systems, including Pattern.

    `runtime_directory` is intended for embedding and tests.  It defaults to
    the private directory selected by ``MONDAY_RUNTIME_DIR``.
    """
    directory = Path(runtime_directory) if runtime_directory else runtime_dir()
    directory.mkdir(parents=True, exist_ok=True)
    thalamus = Thalamus(runtime_directory=directory)
    systems: Dict[str, Any] = {
        "thalamus": thalamus,
        "conversation": AdaptiveConversationSystem(thalamus=thalamus),
        "notus": DirectNotusProcess(
            storage_path=str(directory / "notus_memory.sqlite3"), thalamus=thalamus
        ),
        "emotion": AdaptiveEmotionProcess(
            state_file=str(directory / "emotional_state.json"), thalamus=thalamus
        ),
        "reasoning": AdaptiveReasoningAdapter(
            thalamus=thalamus,
            **({"reasoner_factory": reasoning_factory} if reasoning_factory else {}),
        ),
        "pattern": AdaptivePatternRecognition(thalamus=thalamus),
        "language": AdaptiveLanguageGenerator(thalamus=thalamus),
        "output": AdaptiveOutputLobe(thalamus=thalamus, enable_tts=False),
    }
    for name in ("conversation", "notus", "emotion", "reasoning", "pattern", "language", "output"):
        result = thalamus.register_lobe(name, systems[name])
        if result["status"] != "success":
            raise RuntimeError(f"Could not register {name}: {result.get('message')}")
    install_learning_integration(systems)
    install_hardened_stores(systems)
    return systems


def shutdown_core_systems(systems: Dict[str, Any]) -> None:
    for name in ("output", "language", "pattern", "reasoning", "emotion", "notus", "conversation"):
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
