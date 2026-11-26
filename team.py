"""How a lobe works with the rest of her through the Thalamus.

In unison, not in a line. Every lobe hears each moment at the same time, the
same full moment as her senses built it, and takes it in on its own. Each
lobe takes a moment in exactly once.

What a lobe can do here: sign up for announcements (listen), tell everyone who
signed up that something happened (announce), ask another lobe for something
(ask), and read what another lobe fired about a moment (about_moment).

Like a brain: nothing asks, nobody waits, no steps. Every lobe starts on a
moment the instant it hears it, with whatever has reached it, and shares its
take with every other lobe (Thalamus.share). Whenever a lobe it reads from
shares something new, it works its take out again and shares again. When
every lobe has gone quiet she has settled on the moment, and each lobe acts
on its final take once (what it does outside itself is held until then:
`once`). Each lobe also shares how it is right now (state_now) whenever that
changes, and keeps doing so between moments on her steady beat; other lobes
read it with `now` instead of asking.

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
    it is about. Executive Control weighs it against the other lobes' bids.
    While a lobe is working a moment out, its bids are gathered and replace
    its earlier ones as its take changes. Nobody waits on a bid."""
    entry = {"from": source, "impulse": impulse, "strength": strength, "about": about, "user_id": user_id, **more}
    gathering = getattr(_working, "bids", None)
    if gathering is not None:
        gathering.append(entry)
        return
    tell = getattr(thalamus, "tell", None)
    if callable(tell):
        tell("executive_control", "bid", entry, source=source)


# What the lobe working on this thread is doing right now (see TakesIn).
_working = threading.local()


def once(do: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    """Something a lobe does outside itself (tells another lobe, saves to
    memory, announces). While it is still working a moment out, it is held:
    when she settles, only what its final take does is done, once. Otherwise
    it is done now."""
    held = getattr(_working, "acts", None)
    if held is None:
        return do(*args, **kwargs)
    held.append((do, args, kwargs))
    return None


_MISSING = object()
_NOT_KEPT = ("thalamus", "_takes_in", "lock", "_lock", "_settle_lock", "_watch", "_watch_stop", "_thread")


def _copy(value: Any) -> Any:
    import copy
    return copy.deepcopy(value)


def _snapshot(lobe: Any, keeps: Tuple[str, ...]) -> List[Tuple[Any, Dict[str, Any]]]:
    """A copy of what the lobe keeps in itself, to put back before it redoes its take."""
    saved: List[Tuple[Any, Dict[str, Any]]] = []
    for name in keeps:
        if name != "*" and not hasattr(lobe, name):
            saved.append((lobe, {name: _MISSING}))  # it didn't have this yet: it is taken away again
            continue
        owner = lobe if name == "*" else getattr(lobe, name, None)
        if name != "*":
            try:
                saved.append((lobe, {name: _copy(owner)}))
                continue
            except Exception:
                pass  # not copyable as a whole: keep each part of it
        if owner is None or not hasattr(owner, "__dict__"):
            continue
        parts: Dict[str, Any] = {}
        for key, value in list(vars(owner).items()):
            if key in _NOT_KEPT or callable(getattr(value, "process_message", None)) \
                    or type(value).__name__ in ("Thalamus", "LobeInbox"):
                continue
            try:
                parts[key] = _copy(value)
            except Exception:
                continue
        saved.append((owner, parts))
    return saved


def _put_back(saved: List[Tuple[Any, Dict[str, Any]]]) -> None:
    for owner, parts in saved:
        for key, value in parts.items():
            if value is _MISSING:
                if key in getattr(owner, "__dict__", {}):
                    delattr(owner, key)
                continue
            try:
                setattr(owner, key, _copy(value))
            except Exception:
                continue


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


def now(thalamus: Any, me: str, lobe: str) -> Dict[str, Any]:
    """How another lobe is right now, as it last shared it with this lobe
    (it shares whenever it changes). {} if it hasn't shared yet. Never asks."""
    held = getattr(thalamus, "shared_with", None)
    if not callable(held):
        return {}
    try:
        state = (held(me, "now") or {}).get(lobe)
    except Exception:
        return {}
    return dict(state) if isinstance(state, dict) else {}


_ALL = object()  # the lobe used all of what was shared


class _Used(dict):
    """What another lobe shared, as handed to a lobe working out its take. It
    notes which parts the lobe actually uses, so the lobe redoes its take only
    when one of those parts changes (not when the other lobe only echoes)."""

    def __init__(self, made: Dict[str, Any], lobe: str, used: Dict[str, Any]) -> None:
        super().__init__(made)
        self._lobe, self._used = lobe, used
        used.setdefault(lobe, set())

    def _note(self, key: Any) -> None:
        held = self._used.get(self._lobe)
        if held is not _ALL:
            held.add(key)

    def _note_all(self) -> None:
        self._used[self._lobe] = _ALL

    def __getitem__(self, key: Any) -> Any:
        self._note(key)
        return super().__getitem__(key)

    def get(self, key: Any, default: Any = None) -> Any:
        self._note(key)
        return super().get(key, default)

    def __contains__(self, key: Any) -> bool:
        self._note(key)
        return super().__contains__(key)

    def pop(self, key: Any, *default: Any) -> Any:
        self._note(key)
        return super().pop(key, *default)

    def setdefault(self, key: Any, default: Any = None) -> Any:
        self._note(key)
        return super().setdefault(key, default)

    def __iter__(self):
        self._note_all()
        return super().__iter__()

    def keys(self):
        self._note_all()
        return super().keys()

    def items(self):
        self._note_all()
        return super().items()

    def values(self):
        self._note_all()
        return super().values()

    def copy(self) -> Dict[str, Any]:
        self._note_all()
        return dict(super().items())

    def __eq__(self, other: Any) -> bool:
        self._note_all()
        return dict.__eq__(self, other)

    __hash__ = None  # type: ignore[assignment]

    def __len__(self) -> int:
        self._note_all()
        return super().__len__()

    def __bool__(self) -> bool:
        return super().__len__() > 0

    def __reduce_ex__(self, protocol: Any) -> Any:
        self._note_all()
        return (dict, (dict(super().items()),))


def _parts(made: Any, used: Any) -> Any:
    """The parts of a share a lobe used, to tell whether they changed. Whether
    anything had been shared at all always counts (a lobe that found nothing
    yet redoes its take when something comes)."""
    if not isinstance(made, dict):
        return (False, made)
    if used is _ALL:
        return (bool(made), dict(made))
    return (bool(made), {key: made.get(key, _MISSING) for key in used})


def about_moment(thalamus: Any, lobe: str, payload: Dict[str, Any], source: str) -> Dict[str, Any]:
    """What another lobe has shared about this moment so far, as it has reached
    this lobe. Never asks. {} if nothing has reached it yet (a lobe that keeps
    going redoes its take when it does)."""
    made = shared_with_me(thalamus, source, payload).get(lobe)
    made = dict(made) if isinstance(made, dict) else {}
    used = getattr(_working, "used", None)
    if used is not None:
        return _Used(made, lobe, used)
    return made


# Every lobe that takes moments in and fires about them. Executive Control
# decides once all of these (that are part of her and hear the moment) have fired.
FIRES_ABOUT_MOMENTS = ("notus", "attention", "novelty", "pattern", "conversation", "emotion", "reasoning",
                       "language", "social_context", "motor_action", "meta_awareness", "shared_representation")


REDOS_PER_MOMENT = 12  # at most this many times a lobe redoes its take on one moment


class TakesIn:
    """A lobe's way of taking each moment in, the way a brain does it: nothing
    asks and nobody waits.

    A lobe that works like that (it has `settle`) starts on the moment the
    instant it hears it, with whatever has reached it so far, and shares its
    take with every other lobe. Whenever one of the lobes it reads from shares
    something new about the moment, it redoes its take and shares again if its
    take changed. Its take is only worked out, never acted on, while things are
    still changing. When every lobe has gone quiet she has settled on the
    moment (Thalamus says so), and the lobe acts on its final take once: that
    is `settle` (and `then`).

    A lobe not yet working like that takes the moment in once the lobes it
    reads from have shared, and acts then."""

    def __init__(self, lobe: str, take_in: Callable[[Dict[str, Any]], Dict[str, Any]],
                 thalamus: Any = None, reads: Tuple[str, ...] = (),
                 settle: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None,
                 owner: Any = None, keeps: Tuple[str, ...] = ()) -> None:
        self.lobe = lobe
        self._owner = owner      # the lobe itself (what it keeps in itself is put back before a redo)
        self._keeps = tuple(keeps)
        self._take_in = take_in
        self._thalamus = thalamus
        self._reads = tuple(reads)
        self._settle = settle
        self._made: "OrderedDict[str, Optional[Dict[str, Any]]]" = OrderedDict()
        self._waiting: "OrderedDict[str, Tuple[Dict[str, Any], Any]]" = OrderedDict()
        self._open: "OrderedDict[str, Dict[str, Any]]" = OrderedDict()  # moments still changing: payload, then, redos
        self._lock = threading.RLock()

    @property
    def keeps_going(self) -> bool:
        return self._settle is not None

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

    def _keep(self, key: str, made: Optional[Dict[str, Any]]) -> None:
        self._made[key] = made
        while len(self._made) > 30:
            self._made.popitem(last=False)

    def take(self, payload: Dict[str, Any],
             then: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None) -> Dict[str, Any]:
        key = moment_key(payload)
        with self._lock:
            if key in self._made:
                made = self._made[key]
                return {"still_taking_it_in": True} if made is None else made
            if self.keeps_going:
                # Starts now, with whatever has reached it.
                self._open[key] = {"payload": payload, "then": then, "redos": 0, "acts": [],
                                   "saved": _snapshot(self._owner, self._keeps) if self._keeps else []}
                while len(self._open) > 30:
                    self._open.popitem(last=False)
                self._keep(key, None)
            else:
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
                self._keep(key, None)
        if self.keeps_going:
            return self._work_out(key, payload, first=True)
        return self._run(key, payload, then)

    def heard(self, signal: Dict[str, Any]) -> None:
        """Another lobe shared something about a moment."""
        key = str(signal.get("moment") or "")
        if self.keeps_going:
            with self._lock:
                open_ = self._open.get(key)
                if open_ is None or signal.get("from") not in self._reads or self._made.get(key) is None:
                    return
                if open_["redos"] >= REDOS_PER_MOMENT:
                    return
                sender = str(signal.get("from") or "")
                used = (open_.get("used") or {}).get(sender)
            if used is not None:
                # It redoes its take only when a part of this lobe's share that it
                # actually used has changed. Anything else is an echo: no redo.
                parts, then = used
                now_shared = shared_with_me(self._thalamus, self.lobe, open_["payload"]).get(sender)
                if _parts(now_shared, parts) == then:
                    _trace("echo_not_redone", lobe=self.lobe, moment=key, because=sender)
                    return
            pending = getattr(self._thalamus, "pending_signals", None)
            if callable(pending) and pending(self.lobe, key, self._reads):
                return  # more is on its way: it redoes its take once, with all of it
            with self._lock:
                open_["redos"] += 1
            self._work_out(key, open_["payload"], first=False, because=str(signal.get("from")))
            return
        with self._lock:
            waiting = self._waiting.get(key)
        if waiting is not None and not self._still_to_fire(key):
            self.take(*waiting)

    def settled(self, signal: Dict[str, Any]) -> None:
        """She has settled on a moment: the lobe acts on its final take, once."""
        key = str(signal.get("moment") or "")
        with self._lock:
            open_ = self._open.pop(key, None)
            made = self._made.get(key)
        if open_ is None or made is None:
            return
        _trace("acted_on_settled", lobe=self.lobe, moment=key, redos=open_["redos"],
               acts=len(open_["acts"]))
        # What its final take does outside itself, done once now.
        for do, args, kwargs in open_["acts"]:
            try:
                do(*args, **kwargs)
            except Exception as exc:
                _trace("act_failed", lobe=self.lobe, moment=key, error=f"{type(exc).__name__}: {exc}")
        if self._settle is not None:
            self._settle(open_["payload"], made)

    def _work_out(self, key: str, payload: Dict[str, Any], first: bool, because: str = "") -> Dict[str, Any]:
        """Work out its take with what has reached it so far; share it if it changed.
        What it keeps in itself is put back first, so only its final take stays;
        what it would do outside itself is held until she settles; its bids
        replace its earlier ones."""
        with self._lock:
            open_ = self._open.get(key) or {}
        if not first and open_.get("saved"):
            _put_back(open_["saved"])
        _working.acts, _working.bids, _working.used = [], [], {}
        failed: Optional[BaseException] = None
        try:
            made = self._take_in(payload)
            made = made if isinstance(made, dict) else {}
            if open_.get("then") is not None:
                open_["then"](payload, made)
        except Exception as exc:
            failed = exc
            made = {"failed": f"{type(exc).__name__}: {exc}"}
        finally:
            acts, bids, used = _working.acts, _working.bids, _working.used
            _working.acts = _working.bids = _working.used = None
        # What it used of each lobe's share, as it was when it used it.
        seen = shared_with_me(self._thalamus, self.lobe, payload) if self._thalamus is not None else {}
        used_now = {lobe: (parts, _parts(seen.get(lobe), parts)) for lobe, parts in (used or {}).items()}
        with self._lock:
            before = self._made.get(key)
            self._made[key] = made
            if key in self._open:
                self._open[key]["acts"] = acts
                self._open[key]["used"] = used_now
        if bids or not first:
            # Its bids as they stand now, in place of any it made before about this moment.
            moment = payload.get("moment") if isinstance(payload.get("moment"), dict) else {}
            tell = getattr(self._thalamus, "tell", None)
            if callable(tell):
                tell("executive_control", "bids", {"from": self.lobe, "about": words_of(moment),
                                                   "user_id": str(payload.get("user_id") or "default"),
                                                   "bids": bids}, source=self.lobe)
        if first or made != before:
            if not first:
                _trace("redid_take", lobe=self.lobe, moment=key, because=because)
            fire(self._thalamus, self.lobe, payload, made)
        if failed is not None:
            raise failed
        return made

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


def nothing_more(_payload: Dict[str, Any], _made: Dict[str, Any]) -> None:
    """For a lobe whose take is all it does: when she settles there is nothing
    more for it to do (what it does outside itself is held with `once`)."""
    return None


def take_moment(lobe: Any, name: str, take_in: Callable[[Dict[str, Any]], Dict[str, Any]],
                payload: Dict[str, Any],
                then: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None,
                reads: Tuple[str, ...] = (),
                settle: Optional[Callable[[Dict[str, Any], Dict[str, Any]], None]] = None,
                keeps: Tuple[str, ...] = ()) -> Dict[str, Any]:
    """This lobe takes the moment in. With `settle`, it starts now, redoes its
    take as the lobes it reads from share, and acts (`settle`, `then`) once she
    has settled. Without it, it waits for the lobes it reads from."""
    taker = lobe.__dict__.get("_takes_in")
    if taker is None:
        taker = lobe.__dict__.setdefault(
            "_takes_in", TakesIn(name, take_in, getattr(lobe, "thalamus", None), reads, settle, lobe, keeps))
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


__all__ = ["listen", "announce", "ask", "bid", "once", "nothing_more", "now", "about_moment", "shared_with_me", "fire", "FIRES_ABOUT_MOMENTS", "moment_key", "TakesIn", "take_moment", "words_of"]
