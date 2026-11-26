"""
Executive Control: picks which of her impulses wins, holds it, and brakes the rest.

There is no list of situations and what to do in each. The options come from
her lobes. A lobe that has something she could do puts in a bid: what its
impulse is, how strong it is by that lobe's own measure, and what it is about.
Executive Control weighs the bids against her own state and the strongest wins:

    score = how strong the bidding lobe says it is
          + how strongly she holds the values the bid says it serves (Values)
          + how strongly she feels right now, for a bid that is about feeling (Emotion)
          + how much of her attention is on what the bid is about (Attention)

Each of those four counts by a weight, and each lobe's bids count by a weight.
Every weight starts at 1, so nothing is favoured. They live in a file in her
runtime folder (executive_weights.json): nobody writes rules into it, and it
is the part learning can tune later.

Then, the way the prefrontal cortex and basal ganglia do it:
- it decides what she says only once every lobe that heard the moment has
  fired about it (nobody is asked; it reacts to their signals);
- one winner per channel (she has one mouth: one thing to say; one thing to do);
- the winner is her purpose: it is held until it is done, and Attention is
  steered to it;
- the losers are braked (should_inhibit), unless one is strong enough to break
  through;
- it watches whether the winner got done (Output reports what she said). If
  what won can't be done, the next strongest takes over;
- something new and stronger switches her to it; what she never answered is
  kept as owed, not lost.

It never does another lobe's work and never tells Language what to say: it
only says which impulse won. Language words it on its own.
"""

from __future__ import annotations

import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


CURRENT_GOAL_SIGNAL_ID = "executive:current_goal"
_LEGACY_GOAL_SIGNAL_PREFIX = "executive:goal:"

# How long a bid stays live without the moment it is about being current (seconds).
_FADE_AFTER = 600.0

# Starting weights: all equal, nothing favoured. "break through" is how strong a
# braked impulse has to be (0 to 1) to act anyway.
_STARTING_WEIGHTS = {"strength": 1.0, "values": 1.0, "feeling": 1.0, "focus": 1.0,
                     "lobes": {}, "break through": 0.8}


def _trace(kind: str, **data: Any) -> None:
    try:
        from trace_monitor import trace_event
        trace_event(kind, **data)
    except Exception:
        pass


def _unit(value: Any, default: float = 0.0) -> float:
    try:
        return max(0.0, min(1.0, float(value)))
    except (TypeError, ValueError):
        return default


class ExecutiveControlLobe:
    """Weighs her lobes' bids, holds the winner, brakes the rest, watches it through."""

    def __init__(self, thalamus: Any = None, weights_path: Optional[str] = None) -> None:
        self.thalamus = thalamus
        self.name = "executive_control"
        self.lock = threading.RLock()
        self._weights_path = weights_path
        self.bids: List[Dict[str, Any]] = []          # live bids, newest last
        self.current: Dict[str, Dict[str, Any]] = {}  # channel -> the winner she is holding
        self.now_about: Dict[str, str] = {}           # user -> what was last said to her
        self.history: List[Dict[str, Any]] = []
        self.held_back: List[Dict[str, Any]] = []
        self.owed: List[Dict[str, Any]] = []          # things she should have answered and didn't
        self.tasks: List[Any] = []
        self.inhibition_state = False
        self._counter = 0

    # ------------------------------------------------------------------
    # The weights (the part learning can tune)
    # ------------------------------------------------------------------

    def _weights_file(self) -> Optional[Path]:
        if self._weights_path:
            return Path(self._weights_path)
        try:
            from runtime_paths import runtime_file
            return Path(runtime_file("executive_weights.json"))
        except Exception:
            return None

    def _weights(self) -> Dict[str, Any]:
        """Read fresh each time, so a change applies at once."""
        weights = json.loads(json.dumps(_STARTING_WEIGHTS))
        path = self._weights_file()
        if path is None:
            return weights
        try:
            if not path.exists():
                path.write_text(json.dumps(_STARTING_WEIGHTS, indent=2), encoding="utf-8")
            saved = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(saved, dict):
                for key in ("strength", "values", "feeling", "focus", "break through"):
                    if key in saved:
                        weights[key] = float(saved[key])
                if isinstance(saved.get("lobes"), dict):
                    weights["lobes"] = {str(k): float(v) for k, v in saved["lobes"].items()}
        except Exception:
            pass
        return weights

    # ------------------------------------------------------------------
    # Bids
    # ------------------------------------------------------------------

    def take_bid(self, bid: Dict[str, Any], sender: str) -> Dict[str, Any]:
        """A lobe has something she could do."""
        impulse = str(bid.get("impulse") or "").strip()
        if not impulse:
            return {"taken": False, "reason": "a bid needs to say what the impulse is"}
        entry = {
            "from": str(bid.get("from") or sender or "a lobe"),
            "impulse": impulse,
            "channel": str(bid.get("channel") or "say"),
            "strength": _unit(bid.get("strength"), 0.5),
            "about": str(bid.get("about") or "").strip(),
            "user_id": str(bid.get("user_id") or "default"),
            "serves": [str(v) for v in bid.get("serves") or [] if str(v).strip()],
            "feeling": bool(bid.get("feeling")),
            "move": bid.get("move"),
            "why": str(bid.get("why") or ""),
            "at": time.time(),
            "status": "live",
        }
        with self.lock:
            now = time.time()
            # One live bid per lobe per impulse about the same thing: a new one replaces it.
            self.bids = [b for b in self.bids if now - b["at"] < _FADE_AFTER and not (
                b["from"] == entry["from"] and b["impulse"] == entry["impulse"]
                and b["about"] == entry["about"] and b["user_id"] == entry["user_id"])][-120:]
            self.bids.append(entry)
            holding = self.current.get(entry["channel"])
        _trace("executive_bid", lobe=entry["from"], impulse=impulse, channel=entry["channel"],
               strength=entry["strength"], about=entry["about"][:120], why=entry["why"])
        if entry["channel"] != "say" or (
                holding and holding.get("status") == "active" and holding.get("about") == entry["about"]):
            # Something to do is decided as it comes in; for something to say, a
            # stronger bid switches her if she is already holding one about this.
            self._decide(entry["user_id"], entry["about"], entry["channel"], "a new bid came in")
        return {"taken": True}

    def take_bids(self, content: Dict[str, Any], sender: str) -> Dict[str, Any]:
        """A lobe's bids about a moment as they stand now: they take the place of
        the bids it made before about the same thing (its take changed)."""
        lobe = str(content.get("from") or sender or "")
        about = str(content.get("about") or "").strip()
        user_id = str(content.get("user_id") or "default")
        with self.lock:
            for b in self.bids:
                if b["from"] == lobe and b["about"] == about and b["user_id"] == user_id and b["status"] == "live":
                    b["status"] = "replaced"
        for entry in content.get("bids") or []:
            if isinstance(entry, dict):
                self.take_bid(entry, lobe)
        return {"taken": True}

    def _state_now(self, bids: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Her own state, asked for once per decision and only if a bid needs it."""
        state: Dict[str, Any] = {"feeling": None, "values": None, "focus": None}
        # Once she has settled on a moment, her feeling and focus are what Emotion
        # and Attention fired about it; nobody is asked.
        moment = self.__dict__.get("_moment_now")
        fired: Dict[str, Dict[str, Any]] = {}
        if moment is not None:
            from team import shared_with_me
            fired = shared_with_me(self.thalamus, self.name, moment)
        if any(b["feeling"] for b in bids):
            felt = fired.get("emotion")
            if felt is None:
                from team import now
                felt = now(self.thalamus, self.name, "emotion")
            state["feeling"] = _unit(felt.get("intensity"))
        if any(b["serves"] for b in bids):
            from team import now
            held = now(self.thalamus, self.name, "values").get("values") or []
            state["values"] = {str(v.get("name") or "").casefold(): _unit(v.get("strength"))
                               for v in held if isinstance(v, dict)}
        focus = fired.get("attention")
        if focus is None:
            from team import now
            focus = now(self.thalamus, self.name, "attention")
        state["focus"] = focus
        return state

    def _score(self, bid: Dict[str, Any], state: Dict[str, Any], weights: Dict[str, Any]) -> Dict[str, Any]:
        lobe_weight = float(weights["lobes"].get(bid["from"], 1.0))
        weighed = {"strength": round(weights["strength"] * lobe_weight * bid["strength"], 3)}
        if bid["serves"] and state.get("values"):
            held = sum(state["values"].get(v.casefold().replace(" ", "_"), state["values"].get(v.casefold(), 0.0))
                       for v in bid["serves"])
            weighed["values"] = round(weights["values"] * held, 3)
        if bid["feeling"] and state.get("feeling") is not None:
            weighed["feeling"] = round(weights["feeling"] * state["feeling"], 3)
        focus = state.get("focus") or {}
        if bid["about"] and str(focus.get("focus_text") or "").strip() == bid["about"]:
            weighed["focus"] = round(weights["focus"] * _unit(focus.get("focus_score")), 3)
        return {"score": round(sum(weighed.values()), 3), "weighed": weighed}

    def _ranked(self, user_id: str, about: str, channel: str) -> List[Dict[str, Any]]:
        with self.lock:
            live = [b for b in self.bids if b["status"] == "live" and b["channel"] == channel
                    and b["user_id"] == user_id and (not about or b["about"] == about)]
        if not live:
            return []
        state, weights = self._state_now(live), self._weights()
        ranked = [{**b, **self._score(b, state, weights)} for b in live]
        # Strongest first; of equals, the one that came in first.
        ranked.sort(key=lambda b: (-b["score"], b["at"]))
        return ranked

    # ------------------------------------------------------------------
    # Decide, hold, switch
    # ------------------------------------------------------------------

    def _decide(self, user_id: str, about: str, channel: str, why: str) -> Optional[Dict[str, Any]]:
        ranked = self._ranked(user_id, about, channel)
        if not ranked:
            return None
        best = ranked[0]
        with self.lock:
            holding = self.current.get(channel)
            if holding and holding.get("status") == "active":
                same = (holding["purpose"], holding["from"], holding["about"]) == (best["impulse"], best["from"], best["about"])
                if same:
                    holding["score"], holding["weighed"] = best["score"], best["weighed"]
                    return holding
                if holding.get("about") == best["about"]:
                    _trace("executive_switched", from_purpose=holding["purpose"], to_purpose=best["impulse"],
                           reason=f"{best['from']}'s bid is stronger ({best['score']} > {holding.get('score')})"
                           if best["score"] > float(holding.get("score") or 0) else why)
                    holding["status"] = "replaced"
                    self._finish(holding)
                else:
                    self._set_aside(holding, "something new came before she answered")
            self._counter += 1
            purpose = {
                "id": self._counter, "purpose": best["impulse"], "from": best["from"], "channel": channel,
                "about": best["about"], "for": user_id, "score": best["score"], "weighed": best["weighed"],
                "move": best.get("move"),
                "status": "active", "started": time.time(), "why": why,
                "others": [{"impulse": b["impulse"], "from": b["from"], "score": b["score"]} for b in ranked[1:]],
            }
            self.current[channel] = purpose
        _trace("executive_decided", purpose=purpose["purpose"], situation=f"{purpose['from']}'s bid won",
               score=purpose["score"], weighed=purpose["weighed"], about=purpose["about"],
               steps=[channel], others=purpose["others"])
        self._steer_attention(purpose)
        return purpose

    def _set_aside(self, purpose: Dict[str, Any], reason: str) -> None:
        """(Call with the lock held.) She moved on before this was done."""
        purpose["status"] = "set aside"
        if purpose.get("channel") == "say":
            # She never answered it: kept as something she still owes, not dropped.
            self.owed.append({"purpose": purpose["purpose"], "about": purpose.get("about"),
                              "for": purpose.get("for"), "since": time.time()})
            self.owed = self.owed[-10:]
            _trace("executive_owed", purpose=purpose["purpose"], about=purpose.get("about"), reason=reason)
        self._finish(purpose)

    def _finish(self, purpose: Dict[str, Any]) -> None:
        """(Call with the lock held.)"""
        self.history.append({**{k: purpose.get(k) for k in ("purpose", "from", "about", "status", "score")},
                             "finished": time.time()})
        self.history = self.history[-50:]
        if self.current.get(purpose.get("channel")) is purpose:
            self.current.pop(purpose["channel"], None)

    def hear_turn(self, user_input: str, user_id: str) -> Dict[str, Any]:
        """Something new was said: bids about anything older no longer compete."""
        with self.lock:
            self.now_about[user_id] = user_input
            for b in self.bids:
                if b["user_id"] == user_id and b["about"] and b["about"] != user_input and b["status"] == "live":
                    b["status"] = "passed"
            for purpose in list(self.current.values()):
                if purpose.get("for") == user_id and purpose.get("about") != user_input \
                        and purpose.get("status") == "active":
                    self._set_aside(purpose, "something new came before she answered")
        return self.get_goal()

    # ------------------------------------------------------------------
    # What she means to say: which impulse won (Language words it on its own)
    # ------------------------------------------------------------------

    def _decide_settled(self, payload: Dict[str, Any], _made: Dict[str, Any]) -> None:
        """She has settled on the moment: decide what she says, and share it."""
        from team import fire
        fire(self.thalamus, self.name, payload, self._settled(payload))

    def _settled(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Every lobe that heard this moment has fired about it (their bids went
        in before they fired): she has settled, and Executive Control decides
        what she means to say. What it decides is fired to every lobe; Language
        words it when it reaches it."""
        from team import words_of
        moment = payload.get("moment") if isinstance(payload.get("moment"), dict) else {}
        said = words_of(moment)
        user_id = str(payload.get("user_id") or moment.get("user_id") or "default")
        if not said:
            return {"say": None, "reason": "nothing was said in this moment"}
        self._moment_now = payload
        return self.what_to_say(user_id, said)

    def what_to_say(self, user_id: str, heard: str = "") -> Dict[str, Any]:
        about = heard or self.now_about.get(user_id, "")
        purpose = self._decide(user_id, about, "say", "Language is ready to word a reply")
        if purpose is None:
            answer = {"say": None, "reason": "no lobe had anything to say about it"}
        else:
            answer = {"say": purpose["purpose"], "purpose": purpose["purpose"], "from": purpose["from"],
                      "options": [purpose["purpose"]] + [o["impulse"] for o in purpose["others"]],
                      "move": purpose.get("move"),
                      "reason": f"{purpose['from']}'s bid won ({purpose['score']})"}
        _trace("executive_say", purpose=answer.get("purpose"), say=answer.get("say"),
               options=answer.get("options"), reason=answer.get("reason"))
        return answer

    def say_failed(self, user_id: str, heard: str, say: str, reason: str) -> Dict[str, Any]:
        """What won couldn't be said: it is out, and the next strongest takes over."""
        about = heard or self.now_about.get(user_id, "")
        with self.lock:
            for b in self.bids:
                if b["status"] == "live" and b["channel"] == "say" and b["user_id"] == user_id \
                        and b["impulse"] == say and (not about or b["about"] == about):
                    b["status"] = "failed"
            holding = self.current.get("say")
            if holding and holding.get("purpose") == say:
                holding["status"] = "failed"
                self._finish(holding)
        _trace("executive_step", purpose=say, step="say", status="changed",
               result=f"couldn't say '{say}': {reason}")
        return self.what_to_say(user_id, heard)

    def _heard_delivery(self, content: Dict[str, Any]) -> None:
        """Output reports what she actually said: the winner is done, or, if she
        said nothing when something had won, it stays owed."""
        text = str(content.get("text") or "").strip()
        with self.lock:
            purpose = self.current.get("say")
            if not purpose or purpose.get("status") != "active":
                return
            if text:
                purpose["status"] = "done"
                result = f"she said: {text}"
            else:
                purpose["status"] = "failed"
                result = "something had won and she said nothing"
                self.owed.append({"purpose": purpose["purpose"], "about": purpose.get("about"),
                                  "for": purpose.get("for"), "since": time.time()})
                self.owed = self.owed[-10:]
                _trace("executive_owed", purpose=purpose["purpose"], about=purpose.get("about"),
                       reason="she said nothing")
            self._finish(purpose)
        _trace("executive_step", purpose=purpose["purpose"], step="say", status=purpose["status"], result=result)

    # ------------------------------------------------------------------
    # The brake
    # ------------------------------------------------------------------

    def should_inhibit(self, action: str, strength: Any = None, serves: str = "", source: str = "") -> Dict[str, Any]:
        result = self._brake(action, strength, serves, source)
        if result["inhibited"]:
            self._held_back(result["action"], source, result["reason"])
        else:
            _trace("executive_allowed", action=result["action"], source=source, reason=result["reason"])
        return result

    def _held_back(self, action: str, source: str, reason: str) -> None:
        """Something was held back by her brake: kept, and seen by the tracer."""
        with self.lock:
            self.held_back.append({"action": action, "from": source, "reason": reason, "at": time.time()})
            self.held_back = self.held_back[-50:]
        _trace("executive_held_back", action=action, source=source, reason=reason)

    def standing_brake(self) -> Dict[str, Dict[str, Any]]:
        """Her brake as it stands right now, for each lobe's plain impulse (one
        that doesn't say how strong it is or what it serves). It is part of how
        she is right now (state_now), so every lobe has it without asking."""
        th = getattr(self, "thalamus", None)
        try:
            with getattr(th, "lobe_handlers_lock", _NullCM()):
                lobes = sorted(getattr(th, "lobe_handlers", None) or {})
        except Exception:
            lobes = []
        breaks_through = float(self._weights()["break through"])
        return {lobe: self._brake(lobe, None, "", lobe, breaks_through) for lobe in lobes if lobe != self.name}

    def _brake(self, action: str, strength: Any = None, serves: str = "", source: str = "",
               breaks_through: Optional[float] = None) -> Dict[str, Any]:
        action_s = (action or "").strip()
        with self.lock:
            holding = [p for p in self.current.values() if p.get("status") == "active"]
            winners = {p["from"] for p in holding}
        purpose = holding[0]["purpose"] if holding else None
        power = _unit(strength)
        if breaks_through is None:
            breaks_through = float(self._weights()["break through"])
        if self.inhibition_state:
            held, reason = True, "everything is on hold"
        elif not holding:
            held, reason = False, "she isn't holding anything it would get in the way of"
        elif source in winners:
            held, reason = False, f"it is {source}'s own impulse that won"
        elif serves and any(serves.casefold() == p["purpose"].casefold() for p in holding):
            held, reason = False, f"it serves what won ({serves})"
        elif power >= breaks_through:
            held, reason = False, f"strong enough ({power:.2f} >= {breaks_through:.2f}) to break through"
        else:
            held, reason = True, f"another impulse won ({purpose}) and this one isn't strong enough to break through"
        return {"action": action_s, "inhibited": held, "allowed": not held, "reason": reason,
                "goal": purpose, "priority": holding[0]["score"] if holding else 0.0}

    # ------------------------------------------------------------------
    # Attention: steered to what won
    # ------------------------------------------------------------------

    def _steer_attention(self, purpose: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if purpose is None or not self._has("attention"):
            return {"steered": False, "reason": "nothing won" if purpose is None else "attention offline"}
        top = max([purpose["score"]] + [o["score"] for o in purpose.get("others") or []] + [1.0])
        signal = {"id": CURRENT_GOAL_SIGNAL_ID,
                  "text": f"{purpose['purpose']}: {purpose.get('about') or ''}".strip(),
                  "source": "executive_control", "modality": "control",
                  "priority": round(min(1.0, purpose["score"] / top), 3),
                  "concepts": ["purpose", purpose["purpose"]]}
        # She tells Attention what won; nobody waits on it.
        self._tell("attention", "remove_signals", {"prefix": _LEGACY_GOAL_SIGNAL_PREFIX})
        told = self._tell("attention", "replace_signals", {"signals": [signal]})
        return {"steered": told, "signal": signal}

    # ------------------------------------------------------------------
    # Team plumbing
    # ------------------------------------------------------------------

    def _has(self, lobe: str) -> bool:
        th = self.thalamus
        if th is None:
            return False
        try:
            with getattr(th, "lobe_handlers_lock", _NullCM()):
                return lobe in (getattr(th, "lobe_handlers", None) or {})
        except Exception:
            return False

    def _tell(self, lobe: str, msg_type: str, payload: Dict[str, Any]) -> bool:
        """Tell another lobe something without waiting for it."""
        if not self._has(lobe):
            return False
        try:
            told = self.thalamus.tell(lobe, msg_type, payload, source="executive_control")
        except Exception:
            return False
        return isinstance(told, dict) and told.get("status") == "delivered"

    def on_joined(self, name: str) -> None:
        self.name = name
        listen = getattr(self.thalamus, "listen", None)
        if callable(listen):
            for topic in ("moment", "delivered"):
                listen(name, topic)

    def shutdown(self) -> None:
        pass

    # ------------------------------------------------------------------
    # What other lobes can ask
    # ------------------------------------------------------------------

    def get_goal(self) -> Dict[str, Any]:
        with self.lock:
            holding = [p for p in self.current.values() if p.get("status") == "active"]
            now = next((p for p in holding if p.get("channel") == "say"), holding[0] if holding else None)
            return {
                "goal": now.get("purpose") if now else None,
                "priority": now.get("score", 0.0) if now else 0.0,
                "detail": now.get("about", "") if now else "",
                "source": now.get("from", "") if now else "",
                "status": now.get("status") if now else None,
                "holding": [{"purpose": p["purpose"], "from": p["from"], "channel": p["channel"]} for p in holding],
                "owed": [{"purpose": o.get("purpose"), "about": o.get("about")} for o in self.owed],
                "inhibited_actions": [],
            }

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return {**self.get_goal(), "live_bids": sum(1 for b in self.bids if b["status"] == "live"),
                    "recent": [{"purpose": h.get("purpose"), "status": h.get("status")} for h in self.history[-5:]],
                    "held_back": self.held_back[-5:], "inhibition_state": self.inhibition_state,
                    "task_count": len(self.tasks)}

    def select_action(self, candidates: List[Any]) -> Dict[str, Any]:
        """Choose among proposed actions: the one that serves what won."""
        with self.lock:
            purposes = [p["purpose"] for p in self.current.values() if p.get("status") == "active"]
        for c in candidates or []:
            if isinstance(c, dict) and any(str(c.get("serves") or "").casefold() == p.casefold() for p in purposes):
                _trace("executive_chose", action=c.get("id") or c.get("action"), purpose=c.get("serves"))
                return {"status": "success", "selected_id": c.get("id"), "goal": c.get("serves"),
                        "reason": f"serves what won ({c.get('serves')})"}
        return {"status": "success", "selected_id": None, "goal": purposes[0] if purposes else None,
                "reason": "no candidate says it serves what won" if purposes else "nothing has won"}

    def reset(self) -> None:
        with self.lock:
            self.bids.clear()
            self.current.clear()
            self.now_about.clear()
            self.history.clear()
            self.held_back.clear()
            self.owed.clear()
            self.tasks.clear()
            self.inhibition_state = False

    def state_now(self) -> Dict[str, Any]:
        """Her goal right now, and her brake as it stands: shared with every lobe
        whenever either changes."""
        return {**self.get_goal(), "brake": self.standing_brake()}

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        content = message.get("content") if isinstance(message.get("content"), dict) else {
            k: v for k, v in message.items() if k not in ("type", "_message_id", "message_id", "source")}
        source = str(message.get("source") or "")
        user_id = str(content.get("user_id") or "default")

        if msg_type == "bid":
            return {"status": "success", "content": self.take_bid(content, source)}
        if msg_type == "bids":
            return {"status": "success", "content": self.take_bids(content, source)}
        if msg_type in ("moment", "about_moment"):
            # In unison: she hears the moment herself. Bids about anything older stop competing.
            from team import words_of
            said = words_of(content.get("moment") if isinstance(content.get("moment"), dict) else {})
            if said:
                self.hear_turn(said, user_id)
                self._moment_now = None  # a new moment: she hasn't settled on it yet
            # It listens while the moment is still changing, and decides once she
            # has settled on it (every lobe's bids are in by then).
            from team import take_moment
            body = take_moment(self, "executive_control", lambda _payload: {}, content,
                               settle=self._decide_settled)
            return {"status": "success", "content": body}
        if msg_type == "delivered":
            self._heard_delivery(content)
            return {"status": "success", "content": {"heard": True}}
        if msg_type == "what_to_say":
            return {"status": "success", "content": self.what_to_say(user_id, str(content.get("heard") or ""))}
        if msg_type == "say_failed":
            body = self.say_failed(user_id, str(content.get("heard") or ""), str(content.get("say") or ""),
                                   str(content.get("reason") or ""))
            return {"status": "success", "content": body}
        if msg_type in ("get_goal", "current_goal"):
            body = self.get_goal()
            return {**body, "status": "success", "content": body}
        if msg_type in ("get_status", "status"):
            body = self.get_status()
            return {**body, "status": "success", "content": body}
        if msg_type in ("should_inhibit", "inhibit_check", "check_inhibition"):
            body = self.should_inhibit(str(content.get("action") or ""), content.get("strength"),
                                       str(content.get("serves") or ""), source)
            return {**body, "status": "success", "content": body}
        if msg_type == "held_back":
            # A lobe held something back by her standing brake: it tells her, nobody waits.
            self._held_back(str(content.get("action") or ""), source, str(content.get("reason") or ""))
            return {"status": "success", "content": {"heard": True}}
        if msg_type in ("steer_attention", "steer"):
            with self.lock:
                now = self.current.get("say") or next(iter(self.current.values()), None)
            body = self._steer_attention(now)
            return {**body, "status": "success", "content": body}
        if msg_type == "select_action":
            return self.select_action(content.get("candidates") or [])
        if msg_type in ("add_task", "report_mistake"):
            task = content.get("task") if "task" in content else content
            if task is None:
                return {"status": "error", "message": "Missing task"}
            with self.lock:
                self.tasks.append(task)
            return {"status": "success", "message": "Task added"}
        if msg_type == "execute_next":
            with self.lock:
                task = None if self.inhibition_state or not self.tasks else self.tasks.pop(0)
            if task is None:
                return {"status": "success", "message": "No task executed (inhibited or empty)"}
            return {"status": "success", "task": task}
        if msg_type == "set_inhibition":
            self.inhibition_state = bool(content.get("state", False))
            return {"status": "success", "inhibition": self.inhibition_state}
        if msg_type == "reset":
            self.reset()
            return {"status": "success", "content": {"message": "ExecutiveControlLobe reset"}}
        if msg_type == "health":
            return {"status": "success", "healthy": True, "content": {"healthy": True}}
        return {"status": "error", "message": f"Unknown message type: {msg_type}", "content": {}}


class _NullCM:
    def __enter__(self) -> "_NullCM":
        return self

    def __exit__(self, *args: Any) -> None:
        return None
