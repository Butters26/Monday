"""Live tracer: watches Monday while she is actually being used.

Turn on by setting MONDAY_TRACE before starting her (REPL or chat daemon):
  MONDAY_TRACE=1                -> writes <runtime dir>/trace.jsonl
  MONDAY_TRACE=/path/file.jsonl -> writes there

It changes nothing about her behavior. It records, one JSON line each:
- every message through Thalamus: who REALLY sent it (from the call stack,
  not the self-reported source), who received it, the type, and what the
  receiver did with it (HANDLED / HANDLED_EMPTY / NOT_UNDERSTOOD / REJECTED /
  CRASHED / NO_RECEIVER) and how long it took;
- every turn: what was said, her reply, how long it took, and for a blank
  reply whether it was her choice or a failure (and the first failure seen);
- events lobes report themselves via trace_event() (e.g. reply attempts);
- uncaught errors in any thread, with traceback;
- warning/error lines lobes print (lines with "⚠️", "❌", "Error", "Traceback").

Summarize with:  python trace_report.py [trace.jsonl]
"""

from __future__ import annotations

import inspect
import json
import os
import sys
import threading
import time
import traceback
import uuid
from pathlib import Path
from typing import Any, Dict, Optional

_lock = threading.Lock()
_state: Dict[str, Any] = {"path": None, "turn": None, "lobes": {}, "installed": False}

NOT_UNDERSTOOD_MARKERS = ("unknown message type", "unknown msg", "unknown type", "unsupported",
                          "not supported", "no handler", "unrecognized")
_PRINT_MARKERS = ("⚠️", "❌", "Error", "error:", "Traceback", "Exception")


def enabled() -> bool:
    return _state["path"] is not None


def trace_event(kind: str, **data: Any) -> None:
    """Lobes call this to report something. No-op when tracing is off."""
    if not enabled():
        return
    _write({"kind": kind, **data})


def _write(record: Dict[str, Any]) -> None:
    record.setdefault("ts", time.time())
    record.setdefault("turn", _state["turn"])
    record.setdefault("thread", threading.current_thread().name)
    line = json.dumps(record, default=str)
    with _lock:
        with open(_state["path"], "a", encoding="utf-8") as handle:
            handle.write(line + "\n")


def _real_sender(thalamus: Any) -> str:
    frames = inspect.stack()[3:]
    try:
        for info in frames:
            obj = info.frame.f_locals.get("self")
            if obj is None or obj is thalamus:
                continue
            name = _state["lobes"].get(id(obj))
            if name:
                return name
        for info in frames:
            if info.frame.f_locals.get("self") is thalamus:
                if info.function not in ("send_message", "send_and_wait", "broadcast_message", "traced"):
                    return f"thalamus:{info.function}"
        return "unknown"
    finally:
        del frames


def _outcome(known: bool, response: Any, destination: str) -> str:
    if not known:
        return "NO_RECEIVER"
    if not isinstance(response, dict):
        return "HANDLED"
    status = response.get("status")
    message = str(response.get("message") or "").lower()
    if status == "success":
        content = response.get("content")
        empty = not content or (isinstance(content, dict) and not any(
            v not in (None, "", [], {}) for v in content.values()))
        return "HANDLED_EMPTY" if empty else "HANDLED"
    if any(m in message for m in NOT_UNDERSTOOD_MARKERS):
        return "NOT_UNDERSTOOD"
    if message.startswith(f"{destination.lower()}:"):
        return "CRASHED"
    return "REJECTED"


class _Tee:
    """Pass printed output through unchanged; record warning/error lines."""

    def __init__(self, stream: Any, name: str) -> None:
        self._stream = stream
        self._name = name
        self._buf = ""

    def write(self, text: str) -> int:
        written = self._stream.write(text)
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if any(m in line for m in _PRINT_MARKERS):
                try:
                    _write({"kind": "printed_warning", "stream": self._name, "line": line[:500]})
                except Exception:
                    pass
        return written

    def flush(self) -> None:
        self._stream.flush()

    def __getattr__(self, item: str) -> Any:
        return getattr(self._stream, item)


def install(systems: Dict[str, Any], path: Optional[str] = None) -> Optional[str]:
    """Attach the tracer to a running Monday. Returns the trace file path."""
    setting = path or os.environ.get("MONDAY_TRACE", "")
    if not setting or _state["installed"]:
        return _state["path"]
    if setting == "1":
        from runtime_paths import runtime_dir
        setting = str(runtime_dir() / "trace.jsonl")
    Path(setting).parent.mkdir(parents=True, exist_ok=True)
    _state["path"] = setting
    _state["installed"] = True

    thalamus = systems["thalamus"]
    with thalamus.lobe_handlers_lock:
        for name, lobe in thalamus.lobe_handlers.items():
            _state["lobes"][id(lobe)] = name

    original_send = thalamus.send_message

    def traced(destination, msg_type, content=None, source="thalamus"):
        sender = _real_sender(thalamus)
        with thalamus.lobe_handlers_lock:
            known = destination in thalamus.lobe_handlers
        started = time.perf_counter()
        response = original_send(destination, msg_type, content, source)
        outcome = _outcome(known, response, destination)
        _write({
            "kind": "message", "from": sender, "claimed_from": source, "to": destination,
            "type": msg_type, "outcome": outcome,
            "receiver_message": str((response or {}).get("message", ""))[:300] if isinstance(response, dict) else "",
            "ms": round((time.perf_counter() - started) * 1000, 2),
        })
        if outcome in ("CRASHED", "NOT_UNDERSTOOD", "REJECTED", "NO_RECEIVER") and _state.get("turn_failures") is not None:
            _state["turn_failures"].append(f"{sender} -> {destination} [{msg_type}] {outcome}")
        return response

    thalamus.send_message = traced
    # send_and_wait / broadcast call self.send_message, so they are covered too.

    original_turn = thalamus.process_user_input

    def traced_turn(user_input, user_id="default", perception_payload=None):
        turn_id = uuid.uuid4().hex[:8]
        _state["turn"] = turn_id
        _state["turn_failures"] = []
        _write({"kind": "turn_start", "turn": turn_id, "user_id": user_id, "text": user_input})
        started = time.perf_counter()
        error = None
        reply = ""
        try:
            reply = original_turn(user_input, user_id=user_id, perception_payload=perception_payload)
            return reply
        except Exception as exc:
            error = "".join(traceback.format_exception(exc))[-2000:]
            raise
        finally:
            silence = getattr(thalamus, "last_language_silence", None)
            blank = not (isinstance(reply, str) and reply.strip())
            cause = None
            if blank:
                if error:
                    cause = "crash"
                elif silence == "chosen":
                    cause = "her choice"
                elif silence == "failed":
                    cause = "language could not form a reply"
                else:
                    cause = "failure" if _state["turn_failures"] else "unexplained"
            _write({"kind": "turn_end", "turn": turn_id, "reply": reply, "blank": blank,
                    "blank_cause": cause, "failures": list(_state["turn_failures"]),
                    "error": error, "ms": round((time.perf_counter() - started) * 1000, 1)})
            _state["turn"] = None
            _state["turn_failures"] = None

    thalamus.process_user_input = traced_turn

    def on_thread_error(args):
        _write({"kind": "uncaught_error", "where": f"thread {getattr(args.thread, 'name', '?')}",
                "error": "".join(traceback.format_exception(args.exc_type, args.exc_value,
                                                            args.exc_traceback))[-2000:]})
        previous_thread_hook(args)

    previous_thread_hook = threading.excepthook
    threading.excepthook = on_thread_error

    def on_error(exc_type, exc, tb):
        _write({"kind": "uncaught_error", "where": "main",
                "error": "".join(traceback.format_exception(exc_type, exc, tb))[-2000:]})
        previous_hook(exc_type, exc, tb)

    previous_hook = sys.excepthook
    sys.excepthook = on_error

    if not isinstance(sys.stdout, _Tee):
        sys.stdout = _Tee(sys.stdout, "stdout")
    if not isinstance(sys.stderr, _Tee):
        sys.stderr = _Tee(sys.stderr, "stderr")

    _write({"kind": "boot", "lobes": sorted(_state["lobes"].values()), "pid": os.getpid()})
    return setting
