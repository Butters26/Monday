"""Locations for mutable Monday runtime data.

Runtime data must never be written into the source checkout because it can
contain learned memories and conversation-derived state.
"""

from __future__ import annotations

import os
from pathlib import Path


def runtime_dir() -> Path:
    """Return the private directory used for mutable application data."""
    configured_dir = os.environ.get("MONDAY_RUNTIME_DIR")
    path = (
        Path(configured_dir).expanduser()
        if configured_dir
        else Path.home() / ".local" / "state" / "monday"
    )
    path.mkdir(parents=True, exist_ok=True)
    return path


def runtime_file(filename: str) -> str:
    """Return a writable private path for one runtime artifact."""
    return str(runtime_dir() / filename)
