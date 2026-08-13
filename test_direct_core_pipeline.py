"""Deterministic acceptance test for the prompted direct-call core path."""

import random
import shutil
from pathlib import Path

from run_abin import create_core_systems, shutdown_core_systems


def test_prompted_core_path_persists_memory_and_delivers_output():
    random.seed(0)
    private_runtime = Path(".test-runtime-direct-core")
    shutil.rmtree(private_runtime, ignore_errors=True)
    systems = create_core_systems(str(private_runtime))
    try:
        response = systems["thalamus"].process_user_input("Hello Monday, explain memory?")

        assert response
        assert systems["output"].last_output == response
        assert list(systems["thalamus"].lobe_handlers) == [
            "conversation", "notus", "emotion", "reasoning", "language", "output"
        ]
        route_names = [route["to"] for route in systems["thalamus"].message_routes]
        prompted_path = ["conversation", "notus", "emotion", "reasoning", "language", "output"]
        positions = [route_names.index(stage) for stage in prompted_path]
        assert positions == sorted(positions)
        memories = systems["notus"].retrieve_memories("Hello Monday")
        assert any(memory["content"] == "Hello Monday, explain memory?" for memory in memories)
    finally:
        shutdown_core_systems(systems)
        shutil.rmtree(private_runtime, ignore_errors=True)
