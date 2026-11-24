#!/usr/bin/env python3
"""Mercy's Thalamus: the tube between her lobes, with a volume knob.

It carries every message. It reads only the address on a message (who it is
for, what kind it is, who sent it) and never what is inside. It decides
nothing and runs nothing: there is no turn script. Every lobe runs on its own
thread (lobe_inbox.py), hears the announcements it signed up for, and asks
other lobes for what it needs.

What it does:
- delivers a message to the lobe it is addressed to and carries the answer
  back (send_message / send_and_wait), or delivers without waiting (tell);
- delivers an announcement to every lobe that listens for it (listen /
  announce); the lobes choose what they listen for;
- shares what each lobe made of a moment with every other lobe as soon as it
  is ready (share / shared_with), the way parts of a brain fire to each other
  without being asked;
- applies the volume Attention sets (set_volume): of the things told and
  announced to a lobe, louder ones are delivered first and quieter ones wait.
  Nothing is ever dropped. Only Attention can set it;
- keeps track of who is waiting on whom, only so two lobes waiting on each
  other don't lock up (lobe_inbox.py);
- reports every delivery failure to the sender;
- everything it carries is visible to the tracer (trace_monitor.py).
"""

from __future__ import annotations

from collections import deque
from datetime import datetime, timezone
import threading
import time
import uuid
from typing import Any, Dict, Iterable, List, Optional

from lobe_inbox import ANSWER_TIMEOUT_SEC, Letter, LobeInbox, Reply, current_chain, new_chain, next_birth

try:
    from trace_monitor import trace_event as _trace_event
except Exception:  # tracer is optional
    def _trace_event(kind: str, **data: Any) -> None:
        return None


class Thalamus:
    """Carries messages between lobes. Decides nothing."""

    def __init__(self) -> None:
        self.running = True
        self.lobe_handlers: Dict[str, Any] = {}
        self.lobe_handlers_lock = threading.RLock()
        self.lobe_status: Dict[str, str] = {}
        self.message_routes: deque = deque(maxlen=200)
        self.inboxes: Dict[str, LobeInbox] = {}
        self.listeners: Dict[str, List[str]] = {}
        # The volume knob. Attention sets it; Thalamus only applies it.
        self.volume: Dict[str, float] = {}
        # Who is waiting on whom right now (addresses only).
        self._waiting: Dict[str, List[str]] = {}
        self._waiting_lock = threading.Lock()
        self._carried = 0  # how many messages it has carried (to tell when she has gone quiet)

    # ------------------------------------------------------------------
    # Lobes joining
    # ------------------------------------------------------------------

    def register_lobe(self, name: str, lobe: Any) -> Dict[str, Any]:
        if not name or lobe is None:
            return {"status": "error", "message": "A lobe name and handler are required"}
        if not callable(getattr(lobe, "process_message", None)) and not callable(
            getattr(lobe, "process_message_safe", None)
        ):
            return {"status": "error", "message": f"{name} has no message handler"}
        inbox = LobeInbox(name, lobe, self._set_status, volume=self._volume_of, waits_on=self.waits_on)
        with self.lobe_handlers_lock:
            old = self.inboxes.get(name)
            self.lobe_handlers[name] = lobe
            self.lobe_status[name] = "online"
            self.inboxes[name] = inbox
        if old is not None:
            old.stop()
        inbox.start()
        joined = getattr(lobe, "on_joined", None)
        if callable(joined):
            # The lobe signs itself up for the announcements it wants
            # (thalamus.listen); Thalamus doesn't choose them.
            joined(name)
        return {
            "status": "success",
            "content": {"registered": name},
            "registered": name,
        }

    def _has_lobe(self, name: str) -> bool:
        with self.lobe_handlers_lock:
            return name in self.lobe_handlers

    def _set_status(self, name: str, status: str) -> None:
        self.lobe_status[name] = status

    def _caller_inbox(self) -> Optional[LobeInbox]:
        with self.lobe_handlers_lock:
            inboxes = list(self.inboxes.values())
        for inbox in inboxes:
            if inbox.owns_current_thread():
                return inbox
        return None

    # ------------------------------------------------------------------
    # Carrying
    # ------------------------------------------------------------------

    def _post(
        self, destination: str, msg_type: str, content: Optional[Dict[str, Any]], source: str,
        want_answer: bool, chain: Optional[str] = None,
    ):
        """Put one envelope in the destination's inbox. Returns (reply, chain, error)."""
        if content is None:
            content = {}
        if not isinstance(content, dict):
            return None, None, {"status": "error", "message": "Message content must be a dictionary", "content": {}}
        with self.lobe_handlers_lock:
            inbox = self.inboxes.get(destination)
        if inbox is None or not inbox.alive:
            self.lobe_status[destination] = "offline"
            return None, None, {"status": "error", "message": f"Unknown destination: {destination}", "content": {}}
        envelope = {
            "type": msg_type,
            "content": dict(content),
            "source": source,
            "message_id": str(uuid.uuid4()),
        }
        # An ask stays on the asker's chain; something told without waiting
        # starts a new chain for whoever receives it (see lobe_inbox.py).
        chain = chain or (current_chain() if want_answer else None) or new_chain()
        reply = Reply() if want_answer else None
        caller = self._caller_inbox()
        self._carried += 1
        inbox.post(Letter(envelope, reply, chain, sender=caller.name if caller is not None else None))
        return reply, chain, None

    def _await(self, destination: str, reply: Reply, chain: str) -> Dict[str, Any]:
        caller = self._caller_inbox()
        if caller is not None:
            with self._waiting_lock:
                self._waiting.setdefault(caller.name, []).append(destination)
            try:
                answered = caller.wait_while_working(reply, chain, ANSWER_TIMEOUT_SEC)
            finally:
                with self._waiting_lock:
                    stack = self._waiting.get(caller.name) or []
                    if stack:
                        stack.pop()
        else:
            answered = reply.wait(ANSWER_TIMEOUT_SEC)
        if not answered:
            return {
                "status": "error",
                "message": f"No answer from {destination} in {ANSWER_TIMEOUT_SEC:g}s",
                "content": {},
            }
        return reply.value

    def waits_on(self, lobe: str, other: str) -> bool:
        """Is `lobe` waiting on `other`, directly or through other lobes?"""
        with self._waiting_lock:
            seen = set()
            current = lobe
            while current not in seen:
                seen.add(current)
                stack = self._waiting.get(current) or []
                if not stack:
                    return False
                current = stack[-1]
                if current == other:
                    return True
        return False

    def _log_route(self, source: str, destination: str, msg_type: str, status: str) -> None:
        self.message_routes.append(
            {
                "from": source,
                "to": destination,
                "type": msg_type,
                "status": status,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
        )

    def send_message(
        self,
        destination: str,
        msg_type: str,
        content: Optional[Dict[str, Any]] = None,
        source: str = "thalamus",
    ) -> Dict[str, Any]:
        """Deliver one envelope to the destination's inbox and carry its answer back."""
        reply, chain, error = self._post(destination, msg_type, content, source, want_answer=True)
        response = error if error is not None else self._await(destination, reply, chain)
        self._log_route(source, destination, msg_type, response.get("status", "error"))
        return response

    def send_and_wait(
        self,
        destination: str,
        msg_type: str,
        content: Optional[Dict[str, Any]] = None,
        source: str = "thalamus",
    ) -> Dict[str, Any]:
        return self.send_message(destination, msg_type, content or {}, source)

    def tell(
        self,
        destination: str,
        msg_type: str,
        content: Optional[Dict[str, Any]] = None,
        source: str = "thalamus",
        chain: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Deliver one envelope without waiting for an answer."""
        _reply, _chain, error = self._post(destination, msg_type, content, source, want_answer=False, chain=chain)
        status = "error" if error is not None else "delivered"
        self._log_route(source, destination, msg_type, status)
        return error if error is not None else {"status": "delivered", "content": {"to": destination}}

    def listen(self, lobe_name: str, topic: str) -> Dict[str, Any]:
        """A lobe asks to receive every announcement on `topic`."""
        with self.lobe_handlers_lock:
            names = self.listeners.setdefault(topic, [])
            if lobe_name not in names:
                names.append(lobe_name)
        return {"status": "success", "content": {"listening": topic, "lobe": lobe_name}}

    def announce(
        self,
        topic: str,
        content: Optional[Dict[str, Any]] = None,
        source: str = "thalamus",
    ) -> Dict[str, Any]:
        """Deliver an announcement to every lobe that listens for `topic`."""
        with self.lobe_handlers_lock:
            names = [n for n in self.listeners.get(topic, []) if n != source]
        # Every lobe that hears it hears it as of the same moment: none is ahead of another.
        born = next_birth()
        results = {name: self.tell(name, topic, content, source, chain=new_chain(born, index))
                   for index, name in enumerate(names)}
        return {"status": "delivered", "content": {"topic": topic, "to": names, "results": results}}

    def share(
        self,
        source: str,
        moment: str,
        made: Dict[str, Any],
    ) -> Dict[str, Any]:
        """A lobe has finished with a moment: what it made of it reaches every
        other lobe, without any lobe signing up or asking. Like one part of a
        brain firing to every part it is wired to. Each lobe keeps it and uses
        it when it wants; nothing waits on it and nothing is dropped.
        Thalamus doesn't look inside what is shared."""
        if not source or not moment:
            return {"status": "error", "message": "A lobe and a moment are required", "content": {}}
        if not isinstance(made, dict):
            made = {"result": made}
        with self.lobe_handlers_lock:
            inboxes = [(name, inbox) for name, inbox in self.inboxes.items() if name != source]
        reached: List[str] = []
        for name, inbox in inboxes:
            if not inbox.alive:
                continue
            inbox.hold(source, moment, made)
            reached.append(name)
        self._carried += 1
        _trace_event("shared", from_lobe=source, moment=moment, to=reached,
                     what=sorted(str(key) for key in made)[:20], empty=not made)
        return {"status": "delivered", "content": {"from": source, "moment": moment, "to": reached}}

    def shared_with(self, lobe: str, moment: str) -> Dict[str, Dict[str, Any]]:
        """Everything the other lobes have shared with `lobe` about a moment so far."""
        with self.lobe_handlers_lock:
            inbox = self.inboxes.get(lobe)
        return inbox.held(moment) if inbox is not None else {}

    def broadcast_message(
        self,
        destinations: Iterable[str],
        msg_type: str,
        content: Optional[Dict[str, Any]] = None,
        source: str = "thalamus",
    ) -> Dict[str, Dict[str, Any]]:
        """Deliver to several lobes at once and carry back each answer."""
        posted = {
            destination: self._post(destination, msg_type, content or {}, source, want_answer=True)
            for destination in destinations
        }
        results: Dict[str, Dict[str, Any]] = {}
        for destination, (reply, chain, error) in posted.items():
            response = error if error is not None else self._await(destination, reply, chain)
            self._log_route(source, destination, msg_type, response.get("status", "error"))
            results[destination] = response
        return results

    # ------------------------------------------------------------------
    # The volume knob (Attention's)
    # ------------------------------------------------------------------

    def set_volume(self, levels: Dict[str, Any]) -> Dict[str, Any]:
        """Attention turns kinds of message up or down.

        `levels` maps a kind of message (its type / announcement topic), or
        "from:<lobe>" for everything a lobe sends, to how loud it is. 1 is
        normal; higher is delivered first; lower waits behind the rest.
        Nothing is dropped at any level. Only Attention can set this.
        """
        caller = self._caller_inbox()
        who = caller.name if caller is not None else None
        if who != "attention":
            _trace_event("thalamus_volume_refused", asked_by=who or "not a lobe",
                         reason="only Attention sets the volume")
            return {"status": "error", "message": "Only Attention sets the volume", "content": {}}
        applied: Dict[str, float] = {}
        for key, value in (levels or {}).items():
            try:
                level = max(0.0, float(value))
            except (TypeError, ValueError):
                continue
            applied[str(key)] = level
        with self.lobe_handlers_lock:
            self.volume.update(applied)
        _trace_event("thalamus_volume", set_by="attention", levels=applied)
        return {"status": "success", "content": {"volume": dict(self.volume)}}

    def _volume_of(self, letter: Letter) -> float:
        volume = self.volume
        if not volume or letter.reply is not None:
            # The knob is for what gets told and announced. A lobe waiting on an
            # answer is never moved ahead of or behind what came before it.
            return 1.0
        kind = volume.get(str(letter.envelope.get("type")))
        if kind is not None:
            return kind
        if letter.sender:
            return volume.get(f"from:{letter.sender}", 1.0)
        return 1.0

    # ------------------------------------------------------------------
    # For whoever is outside her (the chat window, the tracer)
    # ------------------------------------------------------------------

    def is_quiet(self) -> bool:
        """No lobe has a message waiting or is in the middle of one."""
        with self.lobe_handlers_lock:
            inboxes = list(self.inboxes.values())
        return all(inbox.idle for inbox in inboxes)

    def wait_until_quiet(self, timeout: float = ANSWER_TIMEOUT_SEC) -> bool:
        deadline = time.monotonic() + timeout
        carried_when_quiet = None
        while time.monotonic() < deadline:
            carried = self._carried
            if self.is_quiet() and carried == self._carried:
                # Quiet twice in a row with nothing carried in between: nothing is on its way.
                if carried_when_quiet == carried:
                    return True
                carried_when_quiet = carried
            else:
                carried_when_quiet = None
            time.sleep(0.005)
        return False

    def handle_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        if msg_type == "health":
            return {
                "status": "success",
                "content": {
                    "thalamus_healthy": True,
                    "lobes": self.lobe_status.copy(),
                },
            }
        return {
            "status": "error",
            "message": f"Unknown type: {msg_type}",
            "content": {},
        }

    def start(self) -> "Thalamus":
        self.running = True
        return self

    def shutdown(self) -> None:
        self.running = False
        with self.lobe_handlers_lock:
            inboxes = list(self.inboxes.values())
        for inbox in inboxes:
            inbox.stop()


_thalamus_instance: Optional[Thalamus] = None
_thalamus_lock = threading.Lock()


def get_thalamus() -> Thalamus:
    global _thalamus_instance
    with _thalamus_lock:
        if _thalamus_instance is None:
            _thalamus_instance = Thalamus()
        return _thalamus_instance


__all__ = ["Thalamus", "get_thalamus"]
