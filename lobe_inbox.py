"""Each lobe's inbox and its own worker, so every lobe runs on its own.

Thalamus delivers a message into the destination lobe's inbox; that lobe's
own thread picks it up and handles it. Nothing here reads or changes what is
inside a message, picks who gets it, or decides anything.

One thread per lobe. A lobe finishes what it is handling before it takes the
next message, and takes messages in the order they arrived, loudest first
(Attention sets how loud; everything is the same loudness until it does).
So a lobe that asks another lobe something after an announcement always gets
an answer that already includes that announcement.

Chains: a chain is one line of asking. A lobe that asks another lobe something
passes its chain along, so every ask that comes out of that ask is on the same
chain. Anything told without waiting for an answer (tell / announce) starts a
new chain for whoever receives it. Chains are numbered in the order they
start, so an older chain has a smaller number.

While a lobe waits for an answer it handles only:
  1. messages on its own chain (they come out of its own ask), and
  2. an ask on an OLDER chain from a lobe it is itself waiting on, directly or
     through other lobes. That is two lines of asking stuck on each other; the
     lobe working on the newer one serves the older one, so nothing locks up
     and nothing is lost.
Everything else waits its turn.
"""

from __future__ import annotations

import itertools
import os
import threading
import time
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
_chain_numbers = itertools.count(1)


def current_chain() -> Optional[str]:
    return getattr(_current, "chain", None)


def new_chain() -> str:
    """A new chain id. Later chains sort after earlier ones."""
    return f"{next(_chain_numbers):012x}"


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
    __slots__ = ("envelope", "reply", "chain", "posted_at", "sender")

    def __init__(self, envelope: Dict[str, Any], reply: Optional[Reply], chain: str,
                 sender: Optional[str] = None) -> None:
        self.envelope = envelope
        self.reply = reply
        self.chain = chain
        self.posted_at = time.perf_counter()
        self.sender = sender  # the lobe whose thread really sent it (None: not a lobe)


class LobeInbox:
    def __init__(
        self,
        name: str,
        lobe: Any,
        on_status: Callable[[str, str], None],
        volume: Optional[Callable[[Letter], float]] = None,
        waits_on: Optional[Callable[[str, str], bool]] = None,
    ) -> None:
        self.name = name
        self.lobe = lobe
        self._on_status = on_status
        self._volume = volume          # how loud Attention has set this letter (Thalamus keeps the knob)
        self._waits_on = waits_on      # is this lobe waiting on that lobe, directly or through others
        self._letters: Deque[Letter] = deque()
        self._cond = threading.Condition()
        self._running = True
        self.handled = 0
        self._depth = 0   # messages this lobe is in the middle of handling
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

    @property
    def idle(self) -> bool:
        """Nothing waiting and nothing being handled."""
        with self._cond:
            return not self._letters and self._depth == 0

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

    def _loudness(self, letter: Letter) -> float:
        if self._volume is None:
            return 1.0
        try:
            return float(self._volume(letter))
        except Exception:
            return 1.0

    def _next(self) -> Optional[Letter]:
        """The next letter in turn: loudest first, then the one that came first.
        (Call with the condition held.)"""
        if not self._letters:
            return None
        best_index, best = 0, self._loudness(self._letters[0])
        for index in range(1, len(self._letters)):
            loud = self._loudness(self._letters[index])
            if loud > best:
                best_index, best = index, loud
        letter = self._letters[best_index]
        del self._letters[best_index]
        if best_index and _trace_enabled():
            _trace_event("thalamus_priority", lobe=self.name, msg_type=letter.envelope.get("type"),
                         sender=letter.sender, volume=best, went_ahead_of=best_index)
        return letter

    def _run(self) -> None:
        self.thread_idents.add(threading.get_ident())
        while self._running:
            with self._cond:
                letter = self._next()
                if letter is None:
                    self._cond.wait(0.5)
                    continue
                self._depth += 1
            try:
                self._handle(letter)
            finally:
                with self._cond:
                    self._depth -= 1

    def _for_me_while_waiting(self, chain: str) -> Optional[Letter]:
        """A letter this lobe must handle now, though it is waiting for an answer.
        (Call with the condition held.)"""
        stuck: Optional[int] = None
        for index, letter in enumerate(self._letters):
            if letter.chain == chain:
                del self._letters[index]
                return letter
            if (stuck is None and letter.reply is not None and letter.sender
                    and letter.chain < chain and self._waits_on is not None):
                stuck = index
        if stuck is not None:
            letter = self._letters[stuck]
            try:
                locked = bool(self._waits_on(self.name, letter.sender))
            except Exception:
                locked = False
            if locked:
                del self._letters[stuck]
                if _trace_enabled():
                    _trace_event("thalamus_unlocked", lobe=self.name, served=letter.envelope.get("type"),
                                 for_lobe=letter.sender,
                                 reason="both were waiting on each other; the older ask is served first")
                return letter
        return None

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
            if _trace_enabled():
                import traceback
                _trace_event("lobe_crashed", lobe=self.name, msg_type=envelope.get("type"),
                             source=envelope.get("source"), error=f"{type(exc).__name__}: {exc}",
                             traceback="".join(traceback.format_exception(exc))[-3000:])
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
        """Called on this lobe's own thread while it waits for an answer."""
        deadline = time.monotonic() + timeout
        reply.waker = self._wake
        try:
            while not reply.done:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                with self._cond:
                    letter = self._for_me_while_waiting(chain) if self._running else None
                    if letter is None:
                        if not reply.done:
                            self._cond.wait(min(remaining, 0.02))
                        continue
                    self._depth += 1
                try:
                    self._handle(letter)
                finally:
                    with self._cond:
                        self._depth -= 1
            return True
        finally:
            reply.waker = None


__all__ = ["ANSWER_TIMEOUT_SEC", "Letter", "LobeInbox", "Reply", "current_chain", "new_chain"]
