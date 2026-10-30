"""Each lobe's inbox and its own worker, so every lobe runs on its own.

Thalamus delivers a message into the destination lobe's inbox; that lobe's
own thread picks it up and handles it. Nothing here reads or changes what is
inside a message, picks who gets it, or decides anything (see
.github/instructions/thalamus.instructions.md).

Back-and-forth chains: every message carries a chain id, inherited from the
message the sender was handling when it sent (a sender that isn't a lobe,
like the turn script or a background loop, starts a new chain). A lobe that is
waiting for an answer keeps handling messages from the SAME chain itself, so
two lobes asking each other never lock up. If messages from OTHER chains pile
up while it waits, a helper worker for that lobe handles them, so two chains
crossing the same lobes in opposite directions don't lock up either. (That
means a lobe can be handling two chains at once, as it could before inboxes
when two callers reached it at the same time.)
"""

from __future__ import annotations

import os
import threading
import time
import uuid
from collections import deque
from typing import Any, Callable, Deque, Dict, Optional

try:
    from trace_monitor import enabled as _trace_enabled, trace_event as _trace_event
except Exception:  # tracer is optional
    def _trace_enabled() -> bool:
        return False

    def _trace_event(kind: str, **data: Any) -> None:
        return None


ANSWER_TIMEOUT_SEC = float(os.environ.get("MONDAY_LOBE_ANSWER_TIMEOUT", "60"))

_current = threading.local()  # .chain = chain id of the message this thread is handling


def current_chain() -> Optional[str]:
    return getattr(_current, "chain", None)


class Reply:
    """Where an answer is left for the lobe that asked."""

    def __init__(self) -> None:
        self._event = threading.Event()
        self.value: Optional[Dict[str, Any]] = None
        self.waker: Optional[Callable[[], None]] = None

    def set(self, value: Dict[str, Any]) -> None:
        self.value = value
        self._event.set()
        waker = self.waker
        if waker is not None:
            waker()

    @property
    def done(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float) -> bool:
        return self._event.wait(timeout)


class Letter:
    __slots__ = ("envelope", "reply", "chain", "posted_at")

    def __init__(self, envelope: Dict[str, Any], reply: Optional[Reply], chain: str) -> None:
        self.envelope = envelope
        self.reply = reply
        self.chain = chain
        self.posted_at = time.perf_counter()


class LobeInbox:
    def __init__(self, name: str, lobe: Any, on_status: Callable[[str, str], None]) -> None:
        self.name = name
        self.lobe = lobe
        self._on_status = on_status
        self._letters: Deque[Letter] = deque()
        self._cond = threading.Condition()
        self._running = True
        self.handled = 0
        self._waiting = 0   # this lobe's threads currently waiting for an answer
        self._helpers = 0   # helper workers currently running
        self.thread_idents: set = set()
        self.thread = threading.Thread(target=self._run, name=f"lobe:{name}", daemon=True)

    # --- delivery -----------------------------------------------------------
    def start(self) -> "LobeInbox":
        self.thread.start()
        return self

    def stop(self) -> None:
        with self._cond:
            self._running = False
            self._cond.notify_all()

    @property
    def alive(self) -> bool:
        return self.thread.is_alive() and self._running

    def post(self, letter: Letter) -> None:
        with self._cond:
            self._letters.append(letter)
            self._cond.notify_all()

    def owns_current_thread(self) -> bool:
        return threading.get_ident() in self.thread_idents

    # --- the lobe's own thread -----------------------------------------------
    def _wake(self) -> None:
        with self._cond:
            self._cond.notify_all()

    def _take(self, chain: Optional[str], timeout: float,
              stop: Optional[Callable[[], bool]] = None) -> Optional[Letter]:
        """Next letter (any, or only from `chain`), waiting up to `timeout`
        or until `stop()` is true."""
        deadline = time.monotonic() + timeout
        with self._cond:
            while self._running:
                if stop is not None and stop():
                    return None
                if chain is None:
                    if self._letters:
                        return self._letters.popleft()
                else:
                    for index, letter in enumerate(self._letters):
                        if letter.chain == chain:
                            del self._letters[index]
                            return letter
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return None
                self._cond.wait(remaining)
        return None

    def _run(self) -> None:
        self.thread_idents.add(threading.get_ident())
        while self._running:
            letter = self._take(None, 0.5)
            if letter is not None:
                self._handle(letter)

    def _helper_needed(self) -> None:
        """Start a helper if letters are queued and every one of this lobe's
        threads is busy waiting for an answer."""
        with self._cond:
            if not self._letters or not self._running or self._helpers >= self._waiting:
                return
            self._helpers += 1
        threading.Thread(target=self._help, name=f"lobe:{self.name}+helper", daemon=True).start()

    def _help(self) -> None:
        ident = threading.get_ident()
        self.thread_idents.add(ident)
        try:
            while self._running:
                letter = self._take(None, 0.0)
                if letter is None:
                    return
                self._handle(letter)
        finally:
            self.thread_idents.discard(ident)
            with self._cond:
                self._helpers -= 1

    def _handle(self, letter: Letter) -> None:
        envelope = letter.envelope
        previous = current_chain()
        _current.chain = letter.chain
        waited_ms = round((time.perf_counter() - letter.posted_at) * 1000, 2)
        started = time.perf_counter()
        try:
            handler = getattr(self.lobe, "process_message", None) or getattr(
                self.lobe, "process_message_safe", None
            )
            response = handler(envelope)
            if not isinstance(response, dict):
                response = {"status": "success", "content": {"result": response}}
            response.setdefault("status", "success")
            if "content" not in response:
                response["content"] = {
                    key: value for key, value in response.items() if key not in {"status", "message"}
                }
            self._on_status(self.name, "online")
        except Exception as exc:
            self._on_status(self.name, "error")
            response = {"status": "error", "message": f"{self.name}: {exc}", "content": {}}
        finally:
            _current.chain = previous
        self.handled += 1
        if _trace_enabled():
            _trace_event(
                "handled", lobe=self.name, msg_type=envelope.get("type"), source=envelope.get("source"),
                answer_wanted=letter.reply is not None, status=response.get("status"),
                waited_ms=waited_ms, ms=round((time.perf_counter() - started) * 1000, 2),
            )
        if letter.reply is not None:
            letter.reply.set(response)
        elif response.get("status") == "error" and _trace_enabled():
            _trace_event("tell_failed", lobe=self.name, msg_type=envelope.get("type"),
                         message=str(response.get("message", ""))[:300])

    def wait_while_working(self, reply: Reply, chain: str, timeout: float) -> bool:
        """Called on this lobe's own thread while it waits for an answer:
        keep handling messages from the same chain until the answer arrives."""
        deadline = time.monotonic() + timeout
        reply.waker = self._wake
        with self._cond:
            self._waiting += 1
        try:
            while not reply.done:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                letter = self._take(chain, min(remaining, 0.05), stop=lambda: reply.done)
                if letter is not None:
                    self._handle(letter)
                elif not reply.done:
                    self._helper_needed()
            return True
        finally:
            reply.waker = None
            with self._cond:
                self._waiting -= 1


def new_chain() -> str:
    return uuid.uuid4().hex[:12]


__all__ = ["ANSWER_TIMEOUT_SEC", "Letter", "LobeInbox", "Reply", "current_chain", "new_chain"]
