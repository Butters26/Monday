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
from output import OutputLobe
from perception import PerceptionLobe
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
    thalamus = Thalamus()
    systems: Dict[str, Any] = {
        "thalamus": thalamus,
        "perception": PerceptionLobe(thalamus=thalamus, autonomous=False),
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
        "output": OutputLobe(thalamus=thalamus, enable_tts=True),
    }
    for name in ("perception", "conversation", "notus", "emotion", "reasoning", "language", "output"):
        result = thalamus.register_lobe(name, systems[name])
        if result["status"] != "success":
            raise RuntimeError(f"Could not register {name}: {result.get('message')}")
    return systems


def shutdown_core_systems(systems: Dict[str, Any]) -> None:
    for name in ("output", "language", "reasoning", "emotion", "notus", "conversation", "perception"):
        shutdown = getattr(systems.get(name), "shutdown", None)
        if callable(shutdown):
            shutdown()
    systems["thalamus"].shutdown()


def main() -> int:
    systems = create_core_systems()
    print("Monday direct-call core ready. Type a message, or press Ctrl-D to exit.")
    print("Commands: /ears (listen once), /eyes (capture once)")
    try:
        while True:
            try:
                user_input = input("> ")
            except EOFError:
                print()
                break
            text = user_input.strip()
            if not text:
                continue
            if text == "/ears":
                heard = systems["thalamus"].send_message("perception", "listen_audio", {}, source="cli")
                if heard.get("status") == "success":
                    content = heard.get("content", {})
                    heard_text = content.get("text", "").strip() if isinstance(content, dict) else ""
                    if heard_text:
                        print(f"[ears] {heard_text}")
                        print(systems["thalamus"].process_user_input(heard_text))
                    else:
                        print("[ears] Heard audio but no text was transcribed.")
                else:
                    print(f"[ears] {heard.get('message', 'No audio detected')}")
                continue
            if text == "/eyes":
                seen = systems["thalamus"].send_message("perception", "capture_visual", {}, source="cli")
                if seen.get("status") == "success":
                    content = seen.get("content", {})
                    concepts = content.get("concepts", {}) if isinstance(content, dict) else {}
                    if concepts:
                        faces = concepts.get("faces_detected", 0)
                        brightness = concepts.get("brightness", 0.0)
                        resolution = concepts.get("resolution", "unknown")
                        observation = (
                            f"I see {faces} face(s), brightness {brightness:.1f}, resolution {resolution}."
                        )
                        print(f"[eyes] {observation}")
                        print(systems["thalamus"].process_user_input(observation))
                    else:
                        print("[eyes] Captured frame but no visual concepts were produced.")
                else:
                    print(f"[eyes] {seen.get('message', 'No visual input')}")
                continue
            print(systems["thalamus"].process_user_input(text))
    except KeyboardInterrupt:
        print()
    finally:
        shutdown_core_systems(systems)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
