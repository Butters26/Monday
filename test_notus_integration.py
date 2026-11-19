"""Notus on the live path: what is said reaches the real Notus store.

(The outage fallback that held memories inside the Thalamus was part of the
turn script and went with it: the Thalamus carries messages and holds nothing.)
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest

from direct_notus import DirectNotusProcess
from run_abin import create_core_systems, shutdown_core_systems


class ControllableNotus:
    """Wrap DirectNotusProcess to simulate error responses or exceptions."""

    def __init__(self, inner: DirectNotusProcess) -> None:
        self.inner = inner
        self.fail_store_with_error = False
        self.fail_query_with_error = False
        self.raise_on_store = False
        self.raise_on_query = False
        self.store_calls: List[Dict[str, Any]] = []
        self.query_calls: List[Dict[str, Any]] = []
        # After N successful stores during flush, start failing (partial retry).
        self.fail_store_after: Optional[int] = None
        self._store_successes = 0

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        payload = message.get("content") if isinstance(message.get("content"), dict) else {}
        if msg_type == "store":
            self.store_calls.append(dict(payload))
            if self.raise_on_store:
                raise RuntimeError("simulated Notus store exception")
            if self.fail_store_with_error:
                return {"status": "error", "message": "simulated Notus store error", "content": {}}
            if self.fail_store_after is not None and self._store_successes >= self.fail_store_after:
                return {"status": "error", "message": "partial flush failure", "content": {}}
            result = self.inner.process_message(message)
            if result.get("status") == "success":
                self._store_successes += 1
            return result
        if msg_type in {"query", "query_context", "get_recent"}:
            self.query_calls.append({"type": msg_type, **dict(payload)})
            if self.raise_on_query:
                raise RuntimeError("simulated Notus query exception")
            if self.fail_query_with_error:
                return {"status": "error", "message": "simulated Notus query error", "content": {}}
            return self.inner.process_message(message)
        return self.inner.process_message(message)

    def on_joined(self, name: str) -> None:
        self.inner.on_joined(name)  # the real Notus signs up for what he hears

    def retrieve_memories(self, *args, **kwargs):
        return self.inner.retrieve_memories(*args, **kwargs)

    def shutdown(self) -> None:
        shutdown = getattr(self.inner, "shutdown", None)
        if callable(shutdown):
            shutdown()


def _factory(tmp_path, controllable: Optional[ControllableNotus] = None):
    holder = {"ctl": controllable}

    def factory(*, thalamus, runtime_directory):
        inner = DirectNotusProcess(
            storage_path=str(Path(runtime_directory) / "notus_memory.sqlite3"),
            thalamus=thalamus,
        )
        ctl = ControllableNotus(inner)
        holder["ctl"] = ctl
        return ctl

    systems = create_core_systems(
        str(tmp_path / "runtime"),
        notus_factory=factory,
        enable_autonomous=False,
    )
    return systems, holder


def test_primary_notus_success_path(tmp_path):
    systems, holder = _factory(tmp_path)
    try:
        reply = systems["outside"].say("hello", user_id="u1")
        assert isinstance(reply, str) and reply.strip()
        assert "trouble remembering" not in reply.lower()
        assert "trouble retrieving" not in reply.lower()
        # The real Notus kept what was said: he heard the moment himself.
        assert systems["thalamus"].wait_until_quiet(30)
        kept = holder["ctl"].retrieve_memories("hello", user_id="u1")
        assert any(m.get("content") == "hello" for m in kept)
    finally:
        shutdown_core_systems(systems)


def test_no_legacy_mercy_memory_apis():
    from thalamus import Thalamus

    t = Thalamus()
    assert not hasattr(t, "mercy_memory")
    assert not hasattr(t, "retrieve_relevant_memory")
    assert not hasattr(t, "sync_memory_to_notus")
    # The Thalamus holds no memories of its own and runs no turn.
    assert not hasattr(t, "notus_fallback")
    assert not hasattr(t, "process_user_input")
