from __future__ import annotations

from typing import Any, Dict

from learning.hardened_store import HardenedLobeLearningStore


def install_hardened_stores(systems: Dict[str, Any]) -> None:
    thalamus = systems["thalamus"]
    for name, lobe in systems.items():
        if name in {"thalamus", "notus"}:
            continue
        lobe._lobe_learning_store = HardenedLobeLearningStore(
            name, runtime_directory=thalamus.learning_runtime_directory
        )
