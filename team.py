"""How a lobe works with the rest of her through the Thalamus.

In unison, not in a line. Every lobe hears each moment at the same time, the
same full moment as her senses built it, and takes it in on its own. No lobe
waits for another to finish before it starts. A lobe that needs what another
lobe makes of the moment asks that lobe about it (about_moment); the lobe
asked takes the moment in right then if it hasn't yet, and answers with what
it made of it. Each lobe takes a moment in exactly once.

What a lobe can do here: sign up for announcements (listen), tell everyone who
signed up that something happened (announce), ask another lobe for something
(ask), and ask another lobe what it made of a moment (about_moment).

Announcements, and who makes them:

  heard_words / heard_sound / saw   Perception: something reached a sense
  moment        Sensory Integration: the moment built from all her senses.
                Every lobe hears this one.
  thought       Reasoning: it has something to say about the moment (Language
                words a reply when there is a thought to word)
  delivered     Output: what she actually said (empty if nothing)
  remembered, social_read, understood, read_again, contradicts, thought_arose:
                what a lobe found, for any lobe that wants to know. Nobody
                waits on these to start.

Besides that, a lobe that has something she could do bids for it (bid):
Executive Control weighs the bids and one wins.

A moment carries "user_id" (who she is with), "recognition_id" (which moment
it is) and "moment" (what her senses built).
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any, Callable, Dict, Optional


def listen(thalamus: Any, name: str, *topics: str) -> None:
    hear = getattr(thalamus, "listen", None)
    if callable(hear):
        for topic in topics:
            hear(name, topic)


def announce(thalamus: Any, topic: str, content: Dict[str, Any], source: str) -> None:
    tell_all = getattr(thalamus, "announce", None)
    if callable(tell_all):
        tell_all(topic, content, source)


def ask(thalamus: Any, lobe: str, msg_type: str, payload: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Ask another lobe; its answer's content, or {} if it couldn't answer
    (not there, didn't understand, failed). Thalamus reports the failure."""
    send = getattr(thalamus, "send_and_wait", None)
    if not callable(send):
        return {}
    try:
        response = send(lobe, msg_type, payload, source=source)
    except Exception:
        return {}
    if not isinstance(response, dict) or response.get("status") != "success":
        return {}
    body = response.get("content")
    if isinstance(body, dict) and body:
        return body
    return {k: v for k, v in response.items() if k not in ("status", "content", "message")}


def bid(thalamus: Any, source: str, impulse: str, strength: Any, about: str, user_id: str,
        **more: Any) -> None:
    """Tell Executive Control this lobe has something she could do: what the
    impulse is, how strong it is by this lobe's own measure (0 to 1), and what
    it is about. Executive Control weighs it against the other lobes' bids."""
    # Asked, not told: the lobe carries on only once Executive Control has taken
    # the bid, so a lobe that has finished with a moment has its bids in.
    send = getattr(thalamus, "send_and_wait", None)
    if callable(send):
        send("executive_control", "bid", {"from": source, "impulse": impulse, "strength": strength,
                                          "about": about, "user_id": user_id, **more}, source=source)


def moment_key(payload: Dict[str, Any]) -> str:
    """Which moment this is."""
    moment = payload.get("moment") if isinstance(payload.get("moment"), dict) else {}
    rid = str(payload.get("recognition_id") or moment.get("recognition_id") or "").strip()
    return rid or f"{payload.get('user_id')}|{words_of(moment)}"


def about_moment(thalamus: Any, lobe: str, payload: Dict[str, Any], source: str) -> Dict[str, Any]:
    """Ask another lobe what it made of this moment. It takes the moment in
    right then if it hasn't yet. {} if it couldn't answer."""
    return ask(thalamus, lobe, "about_moment",
               {"user_id": payload.get("user_id"), "recognition_id": payload.get("recognition_id"),
                "moment": payload.get("moment")}, source)


class TakesIn:
    """A lobe's way of taking each moment in exactly once, whether it heard the
    moment itself or another lobe asked it about the moment first."""

    def __init__(self, lobe: str, take_in: Callable[[Dict[str, Any]], Dict[str, Any]]) -> None:
        self.lobe = lobe
        self._take_in = take_in
        self._made: "OrderedDict[str, Optional[Dict[str, Any]]]" = OrderedDict()
        self._lock = threading.RLock()

    def take(self, payload: Dict[str, Any],
             then: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """`then` runs once, after what the lobe made of the moment is ready for
        anyone who asks (bidding for it, for one: a lobe bids with a finished
        take on the moment, not while another lobe is still waiting on it)."""
        key = moment_key(payload)
        with self._lock:
            if key in self._made:
                made = self._made[key]
                if made is None:
                    # Asked about a moment it is still in the middle of taking in.
                    try:
                        from trace_monitor import trace_event
                        trace_event("asked_midway", lobe=self.lobe, moment=key)
                    except Exception:
                        pass
                    return {"still_taking_it_in": True}
                return made
            self._made[key] = None
            while len(self._made) > 30:
                self._made.popitem(last=False)
        try:
            made = self._take_in(payload)
        except Exception:
            with self._lock:
                self._made.pop(key, None)
            raise
        made = made if isinstance(made, dict) else {}
        with self._lock:
            self._made[key] = made
        if then is not None:
            then(payload, made)
        return made


def take_moment(lobe: Any, name: str, take_in: Callable[[Dict[str, Any]], Dict[str, Any]],
                payload: Dict[str, Any],
                then: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None) -> Dict[str, Any]:
    """What this lobe makes of the moment: taken in now if it hasn't been yet."""
    taker = lobe.__dict__.get("_takes_in")
    if taker is None:
        taker = lobe.__dict__.setdefault("_takes_in", TakesIn(name, take_in))
    return taker.take(payload, then)


def words_of(moment: Dict[str, Any]) -> str:
    """The words in a moment, if it has any (typed or heard)."""
    if not isinstance(moment, dict):
        return ""
    sense = str(moment.get("modality") or "text")
    if sense not in ("text", "audio"):
        return ""
    for key in ("text", "normalized_text", "transcript"):
        value = moment.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


__all__ = ["listen", "announce", "ask", "bid", "about_moment", "moment_key", "TakesIn", "take_moment", "words_of"]
