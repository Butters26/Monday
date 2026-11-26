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
start, so an older chain has a smaller number. Every lobe that hears the same
announcement gets a chain of the same age: they are peers working in unison.

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
from collections import OrderedDict, deque
from typing import Any, Callable, Deque, Dict, Optional

try:
    from trace_monitor import enabled as _trace_enabled, trace_event as _trace_event
except Exception:  # tracer is optional
    def _trace_enabled() -> bool:
        return False

    def _trace_event(kind: str, **data: Any) -> None:
        return None


ANSWER_TIMEOUT_SEC = float(os.environ.get("MERCY_LOBE_ANSWER_TIMEOUT", "60"))
SIGNAL = "signal"    # what another lobe just shared about a moment
SETTLED = "settled"  # every lobe has gone quiet about a moment: she has settled on it
BEAT = "beat"        # her steady beat: every lobe keeps running between moments
SHARED_MOMENTS_KEPT = 30  # how many recent moments a lobe keeps what the others shared about

_current = threading.local()  # .chain = chain id of the message this thread is handling
_chain_numbers = itertools.count(1)


def current_chain() -> Optional[str]:
    return getattr(_current, "chain", None)


def new_chain(born: Optional[int] = None, listener: int = 0) -> str:
    """A new chain id. Later chains sort after earlier ones. One announcement
    gives every lobe that hears it a chain born at the same time (`born`), so
    anything that happens after the announcement is newer than all of them."""
    if born is None:
        born = next(_chain_numbers)
    return f"{born:012x}.{listener:04x}"


def next_birth() -> int:
    return next(_chain_numbers)


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
        on_idle: Optional[Callable[[], None]] = None,
        share_state: Optional[Callable[[str, Dict[str, Any]], None]] = None,
        pass_back: Optional[Callable[[str, Dict[str, Any], Dict[str, Any]], None]] = None,
    ) -> None:
        self.name = name
        self.lobe = lobe
        self._on_status = on_status
        self._volume = volume          # how loud Attention has set this letter (Thalamus keeps the knob)
        self._waits_on = waits_on      # is this lobe waiting on that lobe, directly or through others
        self._on_idle = on_idle        # told whenever this lobe has nothing left to do (Thalamus: has she settled?)
        self._share_state = share_state  # how this lobe is right now goes to every lobe whenever it changes
        self._pass_back = pass_back    # what this lobe made of something passed on to it goes back as a new message
        self._letters: Deque[Letter] = deque()
        self._cond = threading.Condition()
        self._running = True
        self.handled = 0
        self._depth = 0   # messages this lobe is in the middle of handling
        self.thread_idents: set = set()
        self.thread = threading.Thread(target=self._run, name=f"lobe:{name}", daemon=True)
        # What the other lobes made of each moment, as they shared it (Thalamus.share):
        # moment -> {lobe: what it made of it}. The newest moments are kept.
        self._shared: "OrderedDict[str, Dict[str, Dict[str, Any]]]" = OrderedDict()
        self._shared_lock = threading.Lock()

    # --- what the other lobes shared with this one -----------------------------
    def hold(self, from_lobe: str, moment: str, made: Dict[str, Any]) -> None:
        """Keep what another lobe made of a moment. It reaches this lobe the
        moment it is shared, even while this lobe is busy with something else."""
        with self._shared_lock:
            this_moment = self._shared.get(moment)
            if this_moment is None:
                this_moment = self._shared[moment] = {}
                while len(self._shared) > SHARED_MOMENTS_KEPT:
                    self._shared.popitem(last=False)
            this_moment[from_lobe] = made

    def reacts(self) -> bool:
        """Does this lobe do anything when another lobe fires? (It takes moments in
        once what it reads from has fired, or it has its own on_signal.)"""
        return "_takes_in" in getattr(self.lobe, "__dict__", {}) or callable(getattr(self.lobe, "on_signal", None))

    def _react(self, kind: str, signal: Dict[str, Any]) -> Dict[str, Any]:
        """Something reached this lobe that isn't a message to it: another lobe
        shared something, she settled on a moment, or her beat. The lobe reacts
        on its own; nothing answers."""
        taker = getattr(self.lobe, "__dict__", {}).get("_takes_in")
        if kind == SIGNAL:
            if taker is not None:
                taker.heard(signal)
            hook = getattr(self.lobe, "on_signal", None)
        elif kind == SETTLED:
            if taker is not None:
                taker.settled(signal)
            hook = getattr(self.lobe, "on_settled", None)
        else:
            hook = getattr(self.lobe, "on_beat", None)
        if callable(hook):
            hook(signal)
        return {"status": "success", "content": {}}

    def share_state(self) -> None:
        """How this lobe is right now (its state_now), shared with every lobe
        if it changed. Done after everything it handles, so the others always
        have it without asking."""
        state_now = getattr(self.lobe, "state_now", None)
        if self._share_state is None or not callable(state_now):
            return
        try:
            state = state_now()
        except Exception:
            return
        if isinstance(state, dict):
            self._share_state(self.name, state)

    def pending(self, kind: str, moment: Optional[str], senders: Optional[tuple] = None) -> int:
        """How many letters of this kind about this moment (from these lobes, if
        given) are still waiting here."""
        with self._cond:
            return sum(1 for letter in self._letters if letter.envelope.get("type") == kind
                       and (letter.envelope.get("content") or {}).get("moment") == moment
                       and (senders is None or (letter.envelope.get("content") or {}).get("from") in senders))

    def held(self, moment: str) -> Dict[str, Dict[str, Any]]:
        """Everything the other lobes have shared with this one about a moment so far."""
        with self._shared_lock:
            return dict(self._shared.get(moment) or {})

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
                    now_idle = not self._letters and self._depth == 0
                if now_idle and self._on_idle is not None:
                    try:
                        self._on_idle()
                    except Exception:
                        pass

    def _for_me_while_waiting(self, chain: str) -> Optional[Letter]:
        """A letter this lobe must handle now, though it is waiting for an answer.
        (Call with the condition held.)"""
        for index, letter in enumerate(self._letters):
            if letter.chain == chain:
                del self._letters[index]
                return letter
        if self._waits_on is None:
            return None
        for index, letter in enumerate(self._letters):
            # An older ask from a lobe this one is itself waiting on: serve it.
            if letter.reply is None or not letter.sender or not letter.chain < chain:
                continue
            try:
                locked = bool(self._waits_on(self.name, letter.sender))
            except Exception:
                locked = False
            if locked:
                del self._letters[index]
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
            if envelope.get("type") in (SIGNAL, SETTLED, BEAT):
                # Not a message to this lobe: something it reacts to on its own.
                response = self._react(envelope.get("type"), envelope.get("content") or {})
            else:
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
        self.share_state()
        if _trace_enabled():
            _trace_event(
                "handled", lobe=self.name, msg_type=envelope.get("type"), source=envelope.get("source"),
                answer_wanted=letter.reply is not None, status=response.get("status"),
                waited_ms=waited_ms, ms=round((time.perf_counter() - started) * 1000, 2),
            )
        if letter.reply is not None:
            letter.reply.set(response)
        elif isinstance(envelope.get("pass_back"), dict) and self._pass_back is not None:
            # It was passed on, not asked: what this lobe made of it goes back to
            # whoever passed it on, as a message of its own. Nobody waited for it.
            try:
                self._pass_back(self.name, envelope["pass_back"], response)
            except Exception as exc:
                if _trace_enabled():
                    _trace_event("pass_back_failed", lobe=self.name, error=f"{type(exc).__name__}: {exc}")
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


__all__ = ["ANSWER_TIMEOUT_SEC", "SIGNAL", "SETTLED", "BEAT", "Letter", "LobeInbox", "Reply", "current_chain", "new_chain", "next_birth"]
