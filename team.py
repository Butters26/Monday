"""How a lobe works with the rest of her through the Thalamus.

In unison, not in a line. Every lobe hears each moment at the same time, the
same full moment as her senses built it, and takes it in on its own. Each
lobe takes a moment in exactly once.

What a lobe can do here: sign up for announcements (listen), tell everyone who
signed up that something happened (announce), ask another lobe for something
(ask), and read what another lobe fired about a moment (about_moment).

Like a brain, nothing asks. When a lobe has taken a moment in it fires: what
it made of it goes to every other lobe on its own (Thalamus.share). A lobe
that needs what other lobes made of the moment says which lobes it reads
from (take_moment's `reads`) and takes the moment in once they have fired;
about_moment then reads what reached it. shared_with_me shows everything the
others have fired about a moment so far.

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
from typing import Any, Callable, Dict, List, Optional, Tuple


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


def _trace(kind: str, **data: Any) -> None:
    try:
        from trace_monitor import trace_event
        trace_event(kind, **data)
    except Exception:
        pass


def shared_with_me(thalamus: Any, name: str, payload: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Everything the other lobes have fired to this lobe about this moment so
    far: {lobe: what it made of it}."""
    held = getattr(thalamus, "shared_with", None)
    if not callable(held):
        return {}
    try:
        return held(name, moment_key(payload)) or {}
    except Exception:
        return {}


def fire(thalamus: Any, name: str, payload: Dict[str, Any], made: Dict[str, Any]) -> None:
    """This lobe fires: what it made of the moment goes to every other lobe."""
    share = getattr(thalamus, "share", None)
    if not callable(share):
        return
    key = moment_key(payload)
    try:
        share(name, key, made if isinstance(made, dict) else {"result": made})
    except Exception as exc:
        _trace("share_failed", lobe=name, moment=key, error=f"{type(exc).__name__}: {exc}")


def about_moment(thalamus: Any, lobe: str, payload: Dict[str, Any], source: str) -> Dict[str, Any]:
    """What another lobe fired about this moment, as it has reached this lobe.
    Never asks: a lobe that reads from another lobe takes the moment in only
    once that lobe has fired (take_moment's `reads`). {} if it fired nothing."""
    made = shared_with_me(thalamus, source, payload).get(lobe)
    return dict(made) if isinstance(made, dict) else {}


# Every lobe that takes moments in and fires about them. Executive Control
# decides once all of these (that are part of her and hear the moment) have fired.
FIRES_ABOUT_MOMENTS = ("notus", "attention", "novelty", "pattern", "conversation", "emotion", "reasoning",
                       "language", "social_context", "motor_action", "meta_awareness", "shared_representation")


class TakesIn:
    """A lobe's way of taking each moment in, the way a brain does it: nothing
    asks. The lobe takes the moment in once every lobe it reads from has fired
    about it (they reach it as signals), and then fires what it made of it to
    every other lobe. Each moment is taken in exactly once."""

    def __init__(self, lobe: str, take_in: Callable[[Dict[str, Any]], Dict[str, Any]],
                 thalamus: Any = None, reads: Tuple[str, ...] = ()) -> None:
        self.lobe = lobe
        self._take_in = take_in
        self._thalamus = thalamus
        self._reads = tuple(reads)
        self._made: "OrderedDict[str, Optional[Dict[str, Any]]]" = OrderedDict()
        self._waiting: "OrderedDict[str, Tuple[Dict[str, Any], Any]]" = OrderedDict()
        self._lock = threading.RLock()

    def _still_to_fire(self, key: str) -> List[str]:
        """The lobes this one reads from that haven't fired about this moment yet
        (only lobes that are part of her and hear the moment)."""
        th = self._thalamus
        if not self._reads or th is None:
            return []
        held_by = getattr(th, "shared_with", None)
        held = held_by(self.lobe, key) if callable(held_by) else {}
        hearing = set((getattr(th, "listeners", None) or {}).get("moment") or [])
        joined = set(getattr(th, "lobe_handlers", None) or {})
        return [lobe for lobe in self._reads
                if lobe != self.lobe and lobe in joined and lobe in hearing and lobe not in held]

    def take(self, payload: Dict[str, Any],
             then: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        """`then` runs once, when the lobe has made what it makes of the moment,
        before it fires (its bids are in by the time the others hear it)."""
        key = moment_key(payload)
        with self._lock:
            if key in self._made:
                made = self._made[key]
                return {"still_taking_it_in": True} if made is None else made
            missing = self._still_to_fire(key)
            if missing:
                first = key not in self._waiting
                self._waiting[key] = (payload, then)
                while len(self._waiting) > 30:
                    self._waiting.popitem(last=False)
                if first:
                    _trace("waiting_for_signals", lobe=self.lobe, moment=key, waiting_for=missing)
                return {"waiting_for": missing}
            self._waiting.pop(key, None)
            self._made[key] = None
            while len(self._made) > 30:
                self._made.popitem(last=False)
        return self._run(key, payload, then)

    def heard(self, signal: Dict[str, Any]) -> None:
        """Another lobe fired about a moment. If this lobe was waiting on it and
        everything it reads from has now fired, it takes the moment in."""
        key = str(signal.get("moment") or "")
        with self._lock:
            waiting = self._waiting.get(key)
        if waiting is not None and not self._still_to_fire(key):
            self.take(*waiting)

    def _run(self, key: str, payload: Dict[str, Any], then: Any) -> Dict[str, Any]:
        try:
            made = self._take_in(payload)
        except Exception as exc:
            # It still fires, so no lobe that reads from it waits forever.
            made = {"failed": f"{type(exc).__name__}: {exc}"}
            with self._lock:
                self._made[key] = made
            fire(self._thalamus, self.lobe, payload, made)
            raise
        made = made if isinstance(made, dict) else {}
        with self._lock:
            self._made[key] = made
        if then is not None:
            try:
                then(payload, made)
            finally:
                fire(self._thalamus, self.lobe, payload, made)
        else:
            fire(self._thalamus, self.lobe, payload, made)
        return made


def take_moment(lobe: Any, name: str, take_in: Callable[[Dict[str, Any]], Dict[str, Any]],
                payload: Dict[str, Any],
                then: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None,
                reads: Tuple[str, ...] = ()) -> Dict[str, Any]:
    """This lobe takes the moment in once the lobes it reads from have fired
    about it, and fires what it made of it."""
    taker = lobe.__dict__.get("_takes_in")
    if taker is None:
        taker = lobe.__dict__.setdefault(
            "_takes_in", TakesIn(name, take_in, getattr(lobe, "thalamus", None), reads))
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


__all__ = ["listen", "announce", "ask", "bid", "about_moment", "shared_with_me", "fire", "FIRES_ABOUT_MOMENTS", "moment_key", "TakesIn", "take_moment", "words_of"]
