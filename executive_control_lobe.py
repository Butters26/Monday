"""
Executive Control: the conductor of her brain (plans/BUILD_PLAN.md, "Executive
Control: the conductor").

Contract (.github/instructions/executive-control.instructions.md): organizes
purposeful activity; maintains goals, sets priorities among them, chooses
actions, coordinates progress, and inhibits competing impulses. Uses other
lobes' information and proposals to decide what she pursues and in what
order; never does another lobe's specialist work itself.

It runs as a loop, the way the prefrontal cortex does:

1. Workspace (working memory): every lobe's findings come together in one
   live picture of right now; items fade when they stop mattering.
2. Decide: from the workspace, choose her current purpose, weighing what
   Reasoning, Emotion, Values and Social Context report.
3. Plan: break the purpose into steps, each for the lobe whose job it is.
4. Direct: send those requests through Thalamus; results come back into the
   workspace.
5. Hold back: stop impulses that would derail the purpose; a strong enough
   impulse can still win.
6. Monitor: check each step; a failed step changes the plan or the purpose.
7. Switch: something new or bigger interrupts; the old purpose is set aside,
   not lost.

What situations lead to which purpose, how they rank, and their steps are
basic knowledge in an editable file (executive_purposes.txt in her runtime
folder) that Matthew can change. The code only notices the situations other
lobes report and follows the file.
"""

from __future__ import annotations

import json
import re
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional


CURRENT_GOAL_SIGNAL_ID = "executive:current_goal"
_LEGACY_GOAL_SIGNAL_PREFIX = "executive:goal:"

PLACEHOLDER_PURPOSES = """# Executive Control: what she does in each situation (editable; Matthew's to change).
# One line each:  when <situation>: <purpose> | rank <number> | steps: <step>, <step> [| feeling raises it] [| values: <name>, <name>]
# Higher rank comes first. "feeling raises it" adds how strongly she feels to the rank.
# "values:" adds the strength of those values (from the Values lobe) to the rank.
# Situations she can notice (other lobes report them):
#   he asked something / she didn't get what he meant / his move expects one back /
#   he shared a feeling / he told her something / he asked her to do something /
#   a mistake was found / nothing is happening
# Steps she can give out:
#   recall (Notus)  work out (Reasoning)  say (Language)  do (Motor Action)
# "say: A / B" is what she means to say; the first one she has something for is used:
#   what she knows / how she feels / that she doesn't know / what she worked out / ask what he means /
#   his feeling back / what he asked / what he told her / his move back
when she didn't get what he meant: find out what he means | rank 4 | steps: say: ask what he means
when a mistake was found: fix the mistake | rank 4 | steps: work out, say: what she worked out
when he asked something: answer him | rank 3 | steps: recall, work out, say: what she knows / how she feels / that she doesn't know
when he shared a feeling: respond to how he feels | rank 3 | steps: recall, say: his feeling back | feeling raises it
when he asked her to do something: do what he asked | rank 3 | steps: work out, do, say: what he asked
when his move expects one back: answer his move in kind | rank 2 | steps: say: his move back
when he told her something: take in what he told her | rank 1 | steps: recall, work out, say: what he told her / what she knows
when nothing is happening: think things through | rank 0 | steps: recall, work out
# How strong an impulse has to be (0 to 1) to win over her current purpose:
impulse wins at: 0.8
"""

# The first placeholder (Nov 12), before "say" said what to say: a runtime file
# that still matches it exactly was never edited by Matthew and is upgraded.
OLD_PLACEHOLDER_PURPOSES = PLACEHOLDER_PURPOSES.replace(
    """# "say: A / B" is what she means to say; the first one she has something for is used:
#   what she knows / how she feels / that she doesn't know / what she worked out / ask what he means /
#   his feeling back / what he asked / what he told her / his move back
""", "").replace(" | steps: say: ask what he means", " | steps: say").replace(
    "say: what she worked out", "say").replace("say: what she knows / how she feels / that she doesn't know", "say").replace(
    "say: his feeling back", "say").replace("say: what he asked", "say").replace(
    "steps: say: his move back", "steps: say").replace("say: what he told her / what she knows", "say")

# How long something stays in the workspace without being refreshed (seconds),
# and how long she waits with nothing happening before thinking on her own.
_FADE_AFTER = 600.0
_IDLE_AFTER = 120.0
_IDLE_CHECK = 30.0


def _trace(kind: str, **data: Any) -> None:
    try:
        from trace_monitor import trace_event
        trace_event(kind, **data)
    except Exception:
        pass


class ExecutiveControlLobe:
    """The conductor: workspace, decide, plan, direct, hold back, monitor, switch."""

    def __init__(self, thalamus: Any = None, purposes_path: Optional[str] = None) -> None:
        self.thalamus = thalamus
        self.name = "executive_control"
        self.lock = threading.RLock()
        self._purposes_path = purposes_path
        self.workspace: List[Dict[str, Any]] = []
        self.current: Optional[Dict[str, Any]] = None
        self.set_aside: List[Dict[str, Any]] = []
        self.history: List[Dict[str, Any]] = []
        self.held_back: List[Dict[str, Any]] = []
        self.owed: List[Dict[str, Any]] = []  # things she should have answered and didn't
        self._directed: set = set()  # lobes doing a step she asked for right now
        self.tasks: List[Any] = []  # remediation asks (Metacognition) and legacy add_task
        self.inhibition_state = False
        self.last_turn_at = 0.0
        self.last_thought_at = 0.0
        self.running = False
        self._idle_thread: Optional[threading.Thread] = None
        self._counter = 0
        self._load_state()

    # ------------------------------------------------------------------
    # Basic knowledge: the purposes file
    # ------------------------------------------------------------------

    def _purposes_file(self) -> Optional[Path]:
        if self._purposes_path:
            return Path(self._purposes_path)
        try:
            from runtime_paths import runtime_file
            return Path(runtime_file("executive_purposes.txt"))
        except Exception:
            return None

    def _purposes(self) -> Dict[str, Any]:
        """The purpose rules, read fresh each time so Matthew's edits apply at once."""
        path = self._purposes_file()
        text = PLACEHOLDER_PURPOSES
        if path is not None:
            try:
                if not path.exists() or path.read_text(encoding="utf-8") == OLD_PLACEHOLDER_PURPOSES:
                    path.write_text(PLACEHOLDER_PURPOSES, encoding="utf-8")
                text = path.read_text(encoding="utf-8")
            except Exception:
                text = PLACEHOLDER_PURPOSES
        rules: Dict[str, Dict[str, Any]] = {}
        impulse_wins_at = 0.8
        for raw in text.splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            m = re.match(r"impulse wins at:\s*([0-9.]+)", line, re.I)
            if m:
                try:
                    impulse_wins_at = float(m.group(1))
                except ValueError:
                    pass
                continue
            m = re.match(r"when (.+?):\s*(.+)$", line, re.I)
            if not m:
                continue
            situation = m.group(1).strip().casefold()
            parts = [p.strip() for p in m.group(2).split("|")]
            rule: Dict[str, Any] = {"purpose": parts[0], "rank": 0.0, "steps": [], "feeling": False, "values": []}
            for part in parts[1:]:
                low = part.casefold()
                if low.startswith("rank"):
                    try:
                        rule["rank"] = float(low.split()[1])
                    except (IndexError, ValueError):
                        pass
                elif low.startswith("steps:"):
                    rule["steps"] = [s.strip() for s in part.split(":", 1)[1].split(",") if s.strip()]
                elif "feeling raises it" in low:
                    rule["feeling"] = True
                elif low.startswith("values:"):
                    rule["values"] = [v.strip() for v in part.split(":", 1)[1].split(",") if v.strip()]
            rules[situation] = rule
        return {"rules": rules, "impulse_wins_at": impulse_wins_at}

    # ------------------------------------------------------------------
    # 1. Workspace
    # ------------------------------------------------------------------

    def _add(self, kind: str, source: str, content: Dict[str, Any], user_id: str = "default") -> Dict[str, Any]:
        item = {"kind": kind, "from": source, "content": content, "user_id": user_id, "at": time.time()}
        with self.lock:
            self.workspace.append(item)
            now = time.time()
            self.workspace = [w for w in self.workspace if now - w["at"] < _FADE_AFTER][-80:]
        return item

    def _latest(self, kind: str, user_id: Optional[str] = None, since: float = 0.0) -> Optional[Dict[str, Any]]:
        with self.lock:
            for item in reversed(self.workspace):
                if item["kind"] == kind and item["at"] >= since and (user_id is None or item["user_id"] == user_id):
                    return item
        return None

    # ------------------------------------------------------------------
    # 2. Decide: the situations other lobes report, and the purpose they call for
    # ------------------------------------------------------------------

    def _situations(self, user_id: str) -> List[str]:
        """What's happening now, as the other lobes report it (newest turn only)."""
        turn = self._latest("turn", user_id) or self._latest("turn")
        since = turn["at"] if turn else 0.0
        found: List[str] = []
        if turn:
            reading = self._reading(turn["content"])
            move, act = reading["move"], reading["speech_act"]
            said = str(turn["content"].get("said") or "")
            # Read from what Conversation and Language actually found (the dialogue
            # move, the speech act, Language's feeling signal), not Conversation's
            # thin "intent" label, which calls any sentence with "it" a request.
            if act == "question" or move == "question" or said.rstrip().endswith("?"):
                found.append("he asked something")
            if act == "imperative" or move == "request":
                found.append("he asked her to do something")
            if reading["feeling"] or move == "affect_share":
                found.append("he shared a feeling")
            if move in ("social_open", "social_close", "social_fragment"):
                found.append("his move expects one back")
            if move in ("assertion", "answer", "correction", "topic_shift") or (
                    act == "declarative" and move not in ("social_open", "social_close")):
                found.append("he told her something")
        understood = self._latest("understood", user_id, since)
        if understood:
            c = understood["content"]
            if c.get("didnt_get"):
                found.append("she didn't get what he meant")
            if c.get("corrected"):
                found.append("a mistake was found")
        social = self._latest("social_read", user_id, since)
        if social:
            s = social["content"]
            if s.get("expects"):
                found.append("his move expects one back")
            if str(s.get("last_cue") or "") == "emotional_share" and s.get("is_social_turn"):
                if "he shared a feeling" not in found:
                    found.append("he shared a feeling")
        if self._latest("mistake", None, since):
            found.append("a mistake was found")
        return list(dict.fromkeys(found))

    @staticmethod
    def _reading(turn_content: Dict[str, Any]) -> Dict[str, Any]:
        """What the other lobes made of his turn: Conversation's dialogue move,
        Language's speech act, Language's feeling signal, and what it's about."""
        und = turn_content.get("understanding") or {}
        packet = und.get("language_understanding") if isinstance(und.get("language_understanding"), dict) else {}
        affect = packet.get("affect") if isinstance(packet.get("affect"), dict) else {}
        about = [str(e) for e in (und.get("entities") or []) if str(e).strip()]
        topic = str(und.get("topic") or "").strip()
        if topic and topic not in about:
            about.insert(0, topic)
        return {
            "move": str(und.get("dialogue_move") or und.get("ask_kind") or "").casefold(),
            "speech_act": str(und.get("speech_act") or packet.get("speech_act") or "").casefold(),
            "feeling": bool(affect.get("present")),
            "about": about,
        }

    def _feeling(self) -> float:
        body = self._ask("emotion", "get_emotional_state", {})
        try:
            return max(0.0, min(1.0, float(body.get("intensity") or 0.0)))
        except (TypeError, ValueError):
            return 0.0

    def _value_strengths(self, names: List[str]) -> float:
        if not names:
            return 0.0
        body = self._ask("values", "get_values", {})
        found = {str(v.get("name") or "").casefold(): v for v in body.get("values") or [] if isinstance(v, dict)}
        total = 0.0
        for name in names:
            v = found.get(name.casefold().replace(" ", "_")) or found.get(name.casefold())
            if v:
                try:
                    total += float(v.get("strength") or 0.0)
                except (TypeError, ValueError):
                    pass
        return total

    def _decide(self, user_id: str, situations: List[str], why: str) -> Optional[Dict[str, Any]]:
        knowledge = self._purposes()
        rules = knowledge["rules"]
        options = []
        unknown = [s for s in situations if s not in rules]
        if unknown:
            _trace("executive_note", note="situations with no purpose in executive_purposes.txt", situations=unknown)
        feeling = None
        for s in situations:
            rule = rules.get(s)
            if not rule:
                continue
            score = float(rule["rank"])
            weighed = {"rank": rule["rank"]}
            if rule["feeling"]:
                feeling = self._feeling() if feeling is None else feeling
                score += feeling
                weighed["feeling"] = round(feeling, 2)
            if rule["values"]:
                v = self._value_strengths(rule["values"])
                score += v
                weighed["values"] = round(v, 2)
            options.append({"situation": s, "purpose": rule["purpose"], "steps": list(rule["steps"]),
                            "score": round(score, 3), "weighed": weighed})
        if not options:
            return None
        options.sort(key=lambda o: -o["score"])
        best = options[0]
        self._counter += 1
        purpose = {
            "id": self._counter,
            "purpose": best["purpose"],
            "situation": best["situation"],
            "score": best["score"],
            "weighed": best["weighed"],
            "for": user_id,
            "about": self._what_its_about(user_id),
            "steps": [self._step(s) for s in best["steps"]],
            "status": "active",
            "started": time.time(),
            "why": why,
            "other_options": [{"purpose": o["purpose"], "score": o["score"]} for o in options[1:]],
        }
        turn = self._latest("turn", user_id) or self._latest("turn")
        if turn:
            r = self._reading(turn["content"])
            purpose["reading"] = {"move": r["move"], "speech_act": r["speech_act"], "feeling": r["feeling"]}
            purpose["topic"] = r["about"]
        return purpose

    @staticmethod
    def _step(text: str) -> Dict[str, Any]:
        """"say: what she knows / that she doesn't know" -> the say step and what to say."""
        text = str(text).strip()
        low = text.casefold()
        if low.startswith("say") and (len(low) == 3 or low[3] in ": "):
            what = [w.strip() for w in text[3:].lstrip(": ").split("/") if w.strip()]
            return {"step": "say", "what": what, "status": "planned"}
        return {"step": text, "status": "planned"}

    def what_to_say(self, user_id: str, heard: str = "") -> Dict[str, Any]:
        """Language asks what she means to say right now; Executive Control decides it
        from her current purpose and what its steps found. Language only words it."""
        with self.lock:
            purpose = self.current
            if not purpose or purpose.get("status") != "active":
                answer = {"say": None, "reason": "she has no purpose right now"}
            elif heard and purpose.get("about") and purpose["about"].strip() != heard.strip():
                answer = {"say": None, "purpose": purpose["purpose"],
                          "reason": f"her purpose is about something else ({purpose.get('about')!r})"}
            else:
                step = next((s for s in purpose["steps"] if s["step"].casefold() == "say"), None)
                if step is None:
                    answer = {"say": None, "purpose": purpose["purpose"], "reason": "her purpose has nothing to say"}
                else:
                    found = {s["step"].casefold(): s for s in purpose["steps"]}
                    has = {
                        "what she knows": any(found.get(k, {}).get("status") == "done" for k in ("recall", "work out")),
                        "what she worked out": found.get("work out", {}).get("status") == "done",
                    }
                    options = step.get("what") or []
                    tried = set(step.get("tried") or [])
                    chosen = next((w for w in options if has.get(w.casefold(), True) and w not in tried), None)
                    answer = {"say": chosen, "purpose": purpose["purpose"], "options": options,
                              "move": (purpose.get("reading") or {}).get("move"),
                              "reason": (f"for '{purpose['purpose']}'" if chosen
                                         else "nothing she could say worked" if tried
                                         else "none of what she could say has anything behind it")}
        _trace("executive_say", purpose=answer.get("purpose"), say=answer.get("say"),
               options=answer.get("options"), reason=answer.get("reason"))
        return answer

    def _what_its_about(self, user_id: str) -> str:
        turn = self._latest("turn", user_id)
        if turn:
            return str(turn["content"].get("said") or "")
        thought = self._latest("thought")
        return str((thought or {}).get("content", {}).get("about") or "")

    # ------------------------------------------------------------------
    # 7. Switch, then 3. plan and 4. direct
    # ------------------------------------------------------------------

    def _take_up(self, purpose: Dict[str, Any]) -> None:
        with self.lock:
            now = self.current
            turn = self._latest("turn")
            since = turn["at"] if turn else 0.0
            for h in reversed(self.history):
                if h.get("purpose") == purpose["purpose"] and h.get("about") == purpose.get("about") \
                        and float(h.get("finished") or 0) >= since:
                    return  # already did this for what's happening now
            if now and now.get("status") == "active":
                same_turn = now.get("about") == purpose.get("about")
                if same_turn and now["purpose"] == purpose["purpose"]:
                    return  # already doing exactly this
                if same_turn and purpose["score"] <= now["score"]:
                    _trace("executive_kept", purpose=now["purpose"], over=purpose["purpose"],
                           reason="the current purpose ranks as high or higher")
                    return
                if same_turn:
                    # Something bigger about the same thing: it takes over.
                    now["status"] = "replaced"
                    self.history.append({**{k: now.get(k) for k in ("purpose", "situation", "about", "status", "steps")},
                                         "finished": time.time()})
                    _trace("executive_switched", from_purpose=now["purpose"], to_purpose=purpose["purpose"],
                           reason=f"{purpose['situation']} ranks higher ({purpose['score']} > {now['score']})")
                else:
                    unsaid = any(s["step"].casefold() == "say" and s["status"] == "waiting" for s in now["steps"])
                    now["status"] = "set aside"
                    if unsaid:
                        # She never answered it: kept as something she still owes, not dropped.
                        self.owed.append({**{k: now.get(k) for k in ("purpose", "situation", "about", "for")},
                                          "since": time.time()})
                        self.owed = self.owed[-10:]
                        _trace("executive_owed", purpose=now["purpose"], about=now.get("about"),
                               reason="something new came before she answered")
                    else:
                        self.set_aside.append(now)
                        self.set_aside = self.set_aside[-10:]
                    _trace("executive_switched", from_purpose=now["purpose"], to_purpose=purpose["purpose"],
                           reason=purpose["why"])
            self.current = purpose
        _trace("executive_decided", purpose=purpose["purpose"], situation=purpose["situation"],
               score=purpose["score"], weighed=purpose["weighed"], about=purpose["about"],
               reading=purpose.get("reading"),
               steps=[s["step"] for s in purpose["steps"]], others=purpose["other_options"])
        self._steer_attention(purpose)
        self._direct(purpose)
        self._save_state()

    def _direct(self, purpose: Dict[str, Any]) -> None:
        """Give each step to the lobe whose job it is; results come back into the workspace."""
        about = purpose.get("about") or ""
        user_id = purpose.get("for") or "default"
        for step in purpose["steps"]:
            if purpose.get("status") != "active":
                break
            kind = step["step"].casefold()
            if kind == "recall":
                topic = " ".join(purpose.get("topic") or [])
                if topic:
                    body = self._ask("notus", "query_facts", {"query": topic, "user_id": user_id, "limit": 10})
                    found = list(body.get("facts") or []) + list(body.get("beliefs") or [])
                    asked = f"what she knows about '{topic}'"
                else:
                    # Nothing specific to look up: what has happened lately.
                    body = self._ask("notus", "get_recent", {"user_id": user_id, "limit": 10})
                    found = list(body.get("memories") or body.get("results") or [])
                    asked = "what happened lately"
                self._add("recalled", "notus", {"about": topic or about, "found": found}, user_id)
                step.update(status="done" if found else "failed",
                            result=f"{len(found)} memories ({asked})" if found else f"nothing remembered ({asked})")
            elif kind == "work out":
                if not about:
                    step.update(status="failed", result="nothing to work out")
                    continue
                body = self._ask("reasoning", "work_out", {"question": about, "user_id": user_id})
                self._add("worked_out", "reasoning", body, user_id)
                answers = body.get("answers") or body.get("conclusions") or body.get("knows") or []
                step.update(status="done" if answers else "failed",
                            result="worked out" if answers else str(body.get("unsure") or "Reasoning couldn't work it out"))
            elif kind == "say":
                # Language does not yet take a purpose to word (on Language's list); the
                # turn script still has Language pick the reply. The step stays open until
                # Output reports what she actually said (see "delivered").
                step.update(status="waiting", result="waiting to hear what she says")
            elif kind == "do":
                with self.lock:
                    self._directed.add("motor_action")
                try:
                    body = self._ask("motor_action", "plan_from_turn",
                                     {"user_input": about, "user_id": user_id, "goal": purpose["purpose"]})
                finally:
                    with self.lock:
                        self._directed.discard("motor_action")
                step.update(status="done" if body else "failed",
                            result="given to Motor Action" if body else "Motor Action didn't take it")
            else:
                step.update(status="failed", result=f"no lobe takes the step '{step['step']}'")
            _trace("executive_step", purpose=purpose["purpose"], step=step["step"],
                   status=step["status"], result=step.get("result"))
        self._monitor(purpose)

    # ------------------------------------------------------------------
    # 6. Monitor
    # ------------------------------------------------------------------

    def _monitor(self, purpose: Dict[str, Any]) -> None:
        steps = purpose["steps"]
        failed = [s for s in steps if s["status"] == "failed"]
        waiting = [s for s in steps if s["status"] == "waiting"]
        if waiting and purpose.get("status") == "active":
            # Not finished until she has actually said it: the purpose stays hers.
            _trace("executive_monitored", purpose=purpose["purpose"], status="active",
                   failed=[f"{s['step']}: {s.get('result')}" for s in failed],
                   waiting=[f"{s['step']}: {s.get('result')}" for s in waiting])
            return
        if steps and len(failed) == len(steps):
            purpose["status"] = "stuck"
        elif not failed and not waiting:
            purpose["status"] = "done"
        else:
            # A step that failed is a gap: recorded, not hidden.
            purpose["status"] = "done with gaps"
        _trace("executive_monitored", purpose=purpose["purpose"], status=purpose["status"],
               failed=[f"{s['step']}: {s.get('result')}" for s in failed],
               waiting=[f"{s['step']}: {s.get('result')}" for s in waiting])
        if purpose["status"] in ("done", "done with gaps", "stuck"):
            self._finish(purpose)

    def _finish(self, purpose: Dict[str, Any]) -> None:
        with self.lock:
            self.history.append({**{k: purpose.get(k) for k in ("purpose", "situation", "about", "status", "steps")},
                                 "finished": time.time()})
            self.history = self.history[-50:]
            if self.current is purpose:
                self.current = None
                # Pick back up what was set aside, if it's still about something current.
                while self.set_aside:
                    old = self.set_aside.pop()
                    if time.time() - float(old.get("started") or 0) < _FADE_AFTER:
                        old["status"] = "active"
                        self.current = old
                        _trace("executive_resumed", purpose=old["purpose"], about=old.get("about"))
                        break
        self._save_state()

    def _heard_delivery(self, content: Dict[str, Any]) -> None:
        """Output reports what she actually said: the open "say" step is done, or,
        if she said nothing when a reply was owed, it failed and stays owed."""
        text = str(content.get("text") or "").strip()
        self._add("said", "output", {"text": text}, str(content.get("user_id") or "default"))
        with self.lock:
            purpose = self.current
            if not purpose or purpose.get("status") != "active":
                return
            step = next((s for s in purpose["steps"]
                         if s["step"].casefold() == "say" and s["status"] == "waiting"), None)
            if step is None:
                return
            if text:
                step.update(status="done", result=f"she said: {text}")
            else:
                step.update(status="failed", result="she owed a reply and said nothing")
                self.owed.append({**{k: purpose.get(k) for k in ("purpose", "situation", "about", "for")},
                                  "since": time.time()})
                self.owed = self.owed[-10:]
                _trace("executive_owed", purpose=purpose["purpose"], about=purpose.get("about"),
                       reason="she said nothing")
            purpose["status"] = "checking"
        _trace("executive_step", purpose=purpose["purpose"], step="say",
               status=step["status"], result=step.get("result"))
        self._monitor(purpose)

    # ------------------------------------------------------------------
    # 5. Hold back
    # ------------------------------------------------------------------

    def should_inhibit(self, action: str, strength: Any = None, serves: str = "", source: str = "") -> Dict[str, Any]:
        action_s = (action or "").strip()
        with self.lock:
            now = self.current
        purpose = now["purpose"] if now and now.get("status") == "active" else None
        try:
            power = float(strength) if strength is not None else 0.0
        except (TypeError, ValueError):
            power = 0.0
        wins_at = self._purposes()["impulse_wins_at"]
        if self.inhibition_state:
            held, reason = True, "everything is on hold"
        elif purpose is None:
            held, reason = False, "no current purpose to protect"
        elif source in self._directed:
            held, reason = False, f"Executive Control asked for it, for the current purpose ({purpose})"
        elif serves and serves.casefold() == purpose.casefold():
            held, reason = False, f"it serves the current purpose ({purpose})"
        elif power >= wins_at:
            held, reason = False, f"strong enough ({power:.2f} >= {wins_at:.2f}) to win over {purpose}"
        else:
            held = True
            reason = (f"it doesn't serve the current purpose ({purpose})" if serves or power
                      else f"it doesn't say it serves the current purpose ({purpose})")
        result = {"action": action_s, "inhibited": held, "allowed": not held, "reason": reason,
                  "goal": purpose, "priority": now.get("score") if now else 0.0}
        if held:
            with self.lock:
                self.held_back.append({"action": action_s, "from": source, "reason": reason, "at": time.time()})
                self.held_back = self.held_back[-50:]
        _trace("executive_held_back" if held else "executive_allowed", action=action_s, source=source, reason=reason)
        return result

    # ------------------------------------------------------------------
    # Attention: her real purpose, nothing invented
    # ------------------------------------------------------------------

    def _steer_attention(self, purpose: Optional[Dict[str, Any]]) -> Dict[str, Any]:
        if purpose is None or not self._has("attention"):
            return {"steered": False, "reason": "no purpose" if purpose is None else "attention offline"}
        top = max([purpose["score"]] + [o["score"] for o in purpose.get("other_options") or []] + [1.0])
        signal = {"id": CURRENT_GOAL_SIGNAL_ID,
                  "text": f"{purpose['purpose']}: {purpose.get('about') or ''}".strip(),
                  "source": "executive_control", "modality": "control",
                  "priority": round(min(1.0, purpose["score"] / top), 3),
                  "concepts": ["purpose", purpose["purpose"]]}
        self._ask("attention", "remove_signals", {"prefix": _LEGACY_GOAL_SIGNAL_PREFIX})
        body = self._ask("attention", "replace_signals", {"signals": [signal]})
        return {"steered": bool(body is not None), "signal": signal}

    # ------------------------------------------------------------------
    # The loop: something new comes into the workspace -> decide again
    # ------------------------------------------------------------------

    def _think_again(self, user_id: str, why: str) -> Optional[Dict[str, Any]]:
        situations = self._situations(user_id)
        purpose = self._decide(user_id, situations, why)
        if purpose is not None:
            self._take_up(purpose)
        return self.current

    def hear_turn(self, user_input: str, understanding: Optional[Dict[str, Any]], user_id: str) -> Dict[str, Any]:
        self.last_turn_at = time.time()
        self._add("turn", "conversation", {"said": user_input, "understanding": understanding or {}}, user_id)
        self._think_again(user_id, "he said something")
        return self.get_goal()

    def _idle_loop(self) -> None:
        while self.running:
            time.sleep(_IDLE_CHECK)
            if not self.running:
                break
            now = time.time()
            if now - self.last_turn_at < _IDLE_AFTER or now - self.last_thought_at < _IDLE_AFTER:
                continue
            with self.lock:
                busy = self.current is not None and self.current.get("status") == "active"
                fresh = [w for w in self.workspace if w["at"] > self.last_thought_at
                         and w["kind"] in ("turn", "understood", "remembered")]
            if busy or not fresh:
                continue
            self.last_thought_at = now
            latest = fresh[-1]
            about = str(latest["content"].get("said") or latest["content"].get("about") or "")
            if not about:
                continue
            self._add("thought", "executive_control", {"about": about}, latest["user_id"])
            purpose = self._decide(latest["user_id"], ["nothing is happening"], "nothing is happening")
            if purpose is not None:
                purpose["about"] = about
                self._take_up(purpose)

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

    def _ask(self, lobe: str, msg_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        if not self._has(lobe):
            return {}
        try:
            resp = self.thalamus.send_and_wait(lobe, msg_type, payload, source="executive_control")
        except Exception:
            return {}
        if not isinstance(resp, dict) or resp.get("status") not in ("success", "delivered"):
            return {}
        body = resp.get("content")
        return body if isinstance(body, dict) else {k: v for k, v in resp.items() if k != "status"}

    def on_joined(self, name: str) -> None:
        self.name = name
        listen = getattr(self.thalamus, "listen", None)
        if callable(listen):
            for topic in ("understood", "social_read", "remembered", "delivered"):
                listen(name, topic)
        self.start()

    def start(self) -> None:
        if self.running:
            return
        self.running = True
        self._idle_thread = threading.Thread(target=self._idle_loop, name="executive-idle", daemon=True)
        self._idle_thread.start()

    def shutdown(self) -> None:
        self.running = False
        self._save_state()

    def _state_file(self) -> Optional[Path]:
        try:
            from runtime_paths import runtime_file
            return Path(runtime_file("executive_state.json"))
        except Exception:
            return None

    def _save_state(self) -> None:
        path = self._state_file()
        if path is None:
            return
        try:
            with self.lock:
                data = {"current": self.current, "set_aside": self.set_aside, "history": self.history[-20:],
                        "counter": self._counter}
            path.write_text(json.dumps(data, default=str), encoding="utf-8")
        except Exception:
            pass

    def _load_state(self) -> None:
        path = self._state_file()
        try:
            if path is not None and path.exists():
                data = json.loads(path.read_text(encoding="utf-8"))
                self.current = data.get("current")
                self.set_aside = list(data.get("set_aside") or [])
                self.history = list(data.get("history") or [])
                self._counter = int(data.get("counter") or 0)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # What other lobes can ask
    # ------------------------------------------------------------------

    def get_goal(self) -> Dict[str, Any]:
        with self.lock:
            now = self.current
            return {
                "goal": now.get("purpose") if now else None,
                "priority": now.get("score", 0.0) if now else 0.0,
                "detail": now.get("about", "") if now else "",
                "source": now.get("situation", "") if now else "",
                "status": now.get("status") if now else None,
                "steps": [dict(s) for s in now.get("steps") or []] if now else [],
                "set_aside": [p.get("purpose") for p in self.set_aside],
                "owed": [{"purpose": o.get("purpose"), "about": o.get("about")} for o in self.owed],
                "inhibited_actions": [],
            }

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            return {**self.get_goal(), "workspace_items": len(self.workspace),
                    "recent": [{"purpose": h.get("purpose"), "status": h.get("status")} for h in self.history[-5:]],
                    "held_back": self.held_back[-5:], "inhibition_state": self.inhibition_state,
                    "task_count": len(self.tasks)}

    def select_action(self, candidates: List[Any]) -> Dict[str, Any]:
        """Choose among proposed actions: the one that serves her current purpose."""
        with self.lock:
            purpose = self.current["purpose"] if self.current else None
        for c in candidates or []:
            if isinstance(c, dict) and purpose and str(c.get("serves") or "").casefold() == purpose.casefold():
                _trace("executive_chose", action=c.get("id") or c.get("action"), purpose=purpose)
                return {"status": "success", "selected_id": c.get("id"), "goal": purpose,
                        "reason": f"serves the current purpose ({purpose})"}
        return {"status": "success", "selected_id": None, "goal": purpose,
                "reason": "no candidate says it serves the current purpose" if purpose else "no current purpose"}

    def reset(self) -> None:
        with self.lock:
            self.workspace.clear()
            self.current = None
            self.set_aside.clear()
            self.history.clear()
            self.held_back.clear()
            self.owed.clear()
            self.tasks.clear()
            self.inhibition_state = False
        self._save_state()

    def process_message(self, message: Dict[str, Any]) -> Dict[str, Any]:
        msg_type = message.get("type")
        content = message.get("content") if isinstance(message.get("content"), dict) else {
            k: v for k, v in message.items() if k not in ("type", "_message_id", "message_id", "source")}
        source = str(message.get("source") or "")
        user_id = str(content.get("user_id") or "default")

        # Announcements she signed up for: new things in the workspace.
        if msg_type == "understood":
            self._add("understood", "reasoning", content, user_id)
            self._think_again(user_id, "Reasoning reported what it made of it")
            return {"status": "success", "content": {"heard": True}}
        if msg_type == "social_read":
            self._add("social_read", "social_context", content, user_id)
            self._think_again(user_id, "Social Context reported the social read")
            return {"status": "success", "content": {"heard": True}}
        if msg_type == "remembered":
            self._add("remembered", "notus", content, user_id)
            return {"status": "success", "content": {"heard": True}}
        if msg_type == "delivered":
            self._heard_delivery(content)
            return {"status": "success", "content": {"heard": True}}

        if msg_type in ("set_goal_from_turn", "derive_goal", "update_from_turn"):
            und = content.get("understanding") if isinstance(content.get("understanding"), dict) else {}
            body = self.hear_turn(str(content.get("user_input") or content.get("text") or ""), und, user_id)
            return {**body, "status": "success", "content": body}
        if msg_type in ("get_goal", "current_goal"):
            body = self.get_goal()
            return {**body, "status": "success", "content": body}
        if msg_type == "say_failed":
            # Language couldn't get it said (Reasoning sent it back every time): the
            # plan changes to the next thing she could say, if there is one.
            with self.lock:
                purpose = self.current
                step = next((st for st in (purpose or {}).get("steps") or [] if st["step"].casefold() == "say"), None)
                if step is not None:
                    step.setdefault("tried", []).append(str(content.get("say") or ""))
            _trace("executive_step", purpose=(purpose or {}).get("purpose"), step="say",
                   status="changed", result=f"couldn't say '{content.get('say')}': {content.get('reason')}")
            body = self.what_to_say(user_id, str(content.get("heard") or ""))
            return {"status": "success", "content": body}
        if msg_type == "what_to_say":
            body = self.what_to_say(user_id, str(content.get("heard") or ""))
            return {"status": "success", "content": body}
        if msg_type in ("get_status", "status"):
            body = self.get_status()
            return {**body, "status": "success", "content": body}
        if msg_type in ("should_inhibit", "inhibit_check", "check_inhibition"):
            body = self.should_inhibit(str(content.get("action") or ""), content.get("strength"),
                                       str(content.get("serves") or ""), source)
            return {**body, "status": "success", "content": body}
        if msg_type in ("steer_attention", "steer"):
            body = self._steer_attention(self.current)
            return {**body, "status": "success", "content": body}
        if msg_type == "select_action":
            return self.select_action(content.get("candidates") or [])
        if msg_type in ("add_task", "report_mistake"):
            task = content.get("task") if "task" in content else content
            if task is None:
                return {"status": "error", "message": "Missing task"}
            with self.lock:
                self.tasks.append(task)
            if isinstance(task, dict) and task.get("type") == "remediate":
                self._add("mistake", source or "meta_cognition", task, user_id)
                self._think_again(user_id, "a mistake was reported")
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
        if msg_type in ("set_goal", "hold_goal"):
            # Another lobe proposes a purpose directly; it competes like any other.
            self._counter += 1
            proposed = {"id": self._counter, "purpose": str(content.get("goal") or "").strip() or "idle",
                        "situation": f"proposed by {source or 'a lobe'}",
                        "score": float(content.get("priority") or 0.0), "weighed": {"proposed": True},
                        "for": user_id, "about": str(content.get("detail") or ""),
                        "steps": [{"step": s, "status": "planned"} for s in content.get("steps") or []],
                        "status": "active", "started": time.time(), "why": f"{source} proposed it",
                        "other_options": []}
            self._take_up(proposed)
            body = self.get_goal()
            return {**body, "status": "success", "content": body}
        if msg_type == "clear_goal":
            with self.lock:
                if self.current:
                    self.current["status"] = "dropped"
                    self.history.append({"purpose": self.current.get("purpose"), "status": "dropped"})
                self.current = None
            body = self.get_goal()
            return {**body, "status": "success", "content": body}
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
