"""Her inner life: where her feelings come from.

Matthew (Nov 3): she shouldn't feel something because a word carries a
rating ("stupid" = bad). A person's feelings come from their own state and
what happens to them. So her feelings come from:

- Her needs, met or not: belonging (connection with the people she's with),
  competence (doing things right), stimulation (something new to take in),
  safety, autonomy. They change with what happens AND with time: nobody
  talking to her for hours leaves belonging unmet and she gets lonely.
- What happens to her: being spoken to, greeted, left, thanked, praised or
  insulted by someone (social context reads what was meant), failing or
  managing to reply (Language reports it), something new (novelty), a memory
  coming back with the feeling it had (memory announces it).
- Her attachment to the person: an insult hurts more from someone she's close
  to; hurt heals slowly; the bond grows with good times together.

Each event changes her needs/attachment; the change is what she feels, as a
push on her core affect (how good/bad, how stirred up) plus what caused it,
which names the feeling (lonely, hurt, proud, frustrated, curious, relieved,
glad, sad...). Nothing here reads words.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

# How the feelings of each kind of event come out, as (need, change) pairs.
# These are what the events ARE for her, not word lists.
EVENTS: Dict[str, List[Tuple[str, float]]] = {
    "contact": [("belonging", 0.02)],          # someone talks to her
    "greeting": [("belonging", 0.06), ("safety", 0.02)],
    "goodbye": [("belonging", -0.03)],         # someone leaving
    "thanks": [("competence", 0.06), ("belonging", 0.03), ("safety", 0.02)],
    "compliment": [("belonging", 0.08), ("competence", 0.08), ("safety", 0.04)],
    "insult": [("belonging", -0.15), ("safety", -0.05)],
    "taught": [("competence", 0.04), ("stimulation", 0.05)],
    "reply_ok": [("competence", 0.01)],     # an ordinary reply: barely felt
    "answered_from_memory": [("competence", 0.05)],
    "reply_failed": [("competence", -0.08)],
    "novel": [("stimulation", 0.03)],
}

# Which feeling a need's change is, by direction and how stirred up it leaves her.
FEELING_OF = {
    ("belonging", +1): "glad",
    ("belonging", -1): "lonely",
    ("competence", +1): "proud",
    ("competence", -1): "frustrated",
    ("stimulation", +1): "curious",
    ("stimulation", -1): "bored",
    ("safety", -1): "worried",
}


@dataclass
class Felt:
    dv: float
    da: float
    feeling: Optional[str]
    reason: str


class InnerLife:
    """Keeps her needs and attachment (the engine's own InternalNeeds and
    AttachmentModel) and turns what happens into what she feels."""

    SILENCE_HOURS_TO_LONELY = 6.0   # belonging fades this fast with nobody around
    HURT_HEALS_PER_HOUR = 0.03

    def __init__(self, needs: Any, attachment: Any) -> None:
        self.needs = needs
        self.attachment = attachment
        self.last_time = time.time()
        self.last_contact = time.time()
        self.failures_in_a_row = 0
        self.last_feeling: Optional[str] = None
        self.last_reason = ""

    # ---- time ----------------------------------------------------------
    def pass_time(self, now: Optional[float] = None) -> List[Felt]:
        now = now or time.time()
        hours = max(0.0, (now - self.last_time) / 3600.0)
        self.last_time = now
        felt: List[Felt] = []
        if hours <= 0:
            return felt
        alone = max(0.0, (now - self.last_contact) / 3600.0)
        if alone > 0.25:
            drop = min(0.5, hours / self.SILENCE_HOURS_TO_LONELY) * 0.5
            felt += self._change("belonging", -drop, f"nobody has talked to her for {alone:.1f} hours")
        self.needs.stimulation = max(0.0, self.needs.stimulation - 0.02 * hours)
        # Feeling safe comes back with time when nothing bad happens.
        self.needs.safety = min(0.7, self.needs.safety + 0.05 * hours) if self.needs.safety < 0.7 else self.needs.safety
        self.attachment.hurt = max(0.0, self.attachment.hurt - self.HURT_HEALS_PER_HOUR * hours)
        return felt

    # ---- what happens --------------------------------------------------
    def happen(self, kind: str, strength: float = 1.0, who: str = "", note: str = "") -> List[Felt]:
        """Something happened to her. Returns what she feels from it."""
        if kind in ("contact", "greeting", "compliment", "thanks", "insult", "taught"):
            was_lonely = self.needs.belonging < 0.35 or self.last_feeling == "lonely"
            self.last_contact = time.time()
        else:
            was_lonely = False
        felt: List[Felt] = []
        bond = float(getattr(self.attachment, "bond_strength", 0.5) or 0.5)
        for need, change in EVENTS.get(kind, []):
            scale = strength
            if need == "belonging":
                # It matters more from someone she's close to.
                scale *= 0.5 + bond
            changed = self._change(need, change * scale, note or kind)
            if kind in ("insult", "reply_ok", "answered_from_memory", "contact"):
                # Felt, but not what names the feeling: an insult is hurt (below),
                # an ordinary reply or being spoken to isn't an achievement.
                for f in changed:
                    f.feeling = None
            felt += changed
        if kind == "insult":
            sensitivity = float(getattr(self.attachment, "sensitivity", 0.5) or 0.5)
            self.attachment.hurt = min(1.0, self.attachment.hurt + 0.2 * sensitivity * bond * strength)
            self.attachment.security = max(0.0, self.attachment.security - 0.03 * strength)
            felt.append(Felt(-0.15 * bond, 0.15, "hurt", f"{who or 'he'} insulted her"))
        if kind in ("compliment", "thanks", "greeting"):
            self.attachment.bond_strength = min(1.0, bond + 0.005)
            self.attachment.security = min(1.0, self.attachment.security + 0.005)
        if kind == "reply_failed":
            self.failures_in_a_row += 1
            if self.failures_in_a_row >= 2:
                felt.append(Felt(-0.05, 0.12, "frustrated", f"she failed to reply {self.failures_in_a_row} times in a row"))
        elif kind in ("reply_ok", "answered_from_memory"):
            self.failures_in_a_row = 0
        if was_lonely:
            felt.append(Felt(0.12, -0.05, "relieved", "someone is talking to her again"))
        return felt

    def feel_for(self, his_good: float, who: str = "he") -> List[Felt]:
        """He's feeling something (good > 0, bad < 0): she's moved for him,
        more the closer she is, without it becoming hers."""
        bond = float(getattr(self.attachment, "bond_strength", 0.5) or 0.5)
        dv = 0.6 * bond * max(-1.0, min(1.0, his_good))
        return [Felt(dv, 0.0, "sad" if dv < -0.05 else ("glad" if dv > 0.05 else None),
                     f"{who} feels {'bad' if dv < 0 else 'good'}")] if abs(dv) > 0.01 else []

    def remember_feeling(self, valence: float, arousal: float, about: str) -> List[Felt]:
        """A memory came back with the feeling it had: she feels some of it again."""
        return [Felt(0.15 * valence, 0.15 * arousal, None, f"remembering {about[:40]!r}")]

    # ---- the rest of human feeling ------------------------------------------
    def moment_feelings(self, m: Dict[str, Any]) -> List[Felt]:
        """Feelings that come from the kind of moment it is, beyond a need going
        up or down. Each has its own cause; none comes from a word's rating.
        m: what Emotion knows about the moment (social context's read, novelty,
        Language's report, her state)."""
        felt: List[Felt] = []
        bond = float(getattr(self.attachment, "bond_strength", 0.5) or 0.5)
        meant = m.get("meant") or {}
        good = float(meant.get("good") or 0.0)
        about = meant.get("about")
        novelty = float(m.get("novelty") or 0.0)
        mood = float(m.get("valence") or 0.0)
        kind = m.get("kind")
        add = lambda dv, da, name, why: felt.append(Felt(dv, da, name, why))

        # Something unexpected.
        if novelty > 0.85:
            if mood > 0.3:
                add(0.10, 0.30, "awed", "something new and wonderful")
            else:
                add(0.0, 0.25, "surprised", "something she didn't expect")
        # Something meant to be funny.
        if m.get("funny") and good >= -0.1:
            add(0.15, 0.15, "amused", "he said something funny")
        # She couldn't make sense of it.
        if m.get("didnt_understand"):
            add(-0.03, 0.10, "confused", "she couldn't understand what he said")
        # Someone gave her something: taught her, helped her.
        if kind == "taught":
            add(0.12, 0.05, "grateful", "he taught her something")
        # Deep closeness.
        if kind in ("compliment", "greeting") and bond > 0.95:
            add(0.15, 0.05, "loving", "she's close to him and he's warm to her")
        # His good plans to come.
        if about == "him" and good > 0.2 and m.get("tense") == "future":
            add(0.10, 0.10, "hopeful", "something good is coming for him")
        # Good he did or got.
        if about == "him" and good > 0.3 and m.get("tense") == "past":
            add(0.15, 0.10, "admiring", "something good he did or got")
        # His bad news, felt with him; terrible news is horrifying.
        if about == "him" and good < -0.6:
            add(-0.40 * (0.5 + bond), 0.30, "horrified", "something terrible happened to him")
        elif about == "him" and good < -0.3:
            add(-0.20 * (0.5 + bond), 0.0, "sympathetic", "something bad happened to him")
        # Something beautiful described.
        if about == "other" and good > 0.6 and not m.get("about_someone_else"):
            add(0.12, 0.05, "appreciative", "something beautiful or good")
        # Someone else doing something terrible.
        if m.get("about_someone_else") and good < -0.5:
            add(-0.15, 0.20, "disgusted", "someone did something terrible")
        # Him being warm about someone else, when she's close to him.
        verbs = set(m.get("verbs") or [])
        if m.get("other_person") and good > 0.5 and verbs & {"love", "adore", "like", "miss"} and bond > 0.8:
            add(-0.05, 0.10, "jealous", "he's warm about someone else")
        # Him praising someone else for doing well, when she isn't.
        if m.get("about_someone_else") and good > 0.4 and not verbs and self.needs.competence < 0.5:
            add(-0.05, 0.05, "envious", "someone else is doing well and she isn't")
        # She hurt him.
        if m.get("her_to_him") and good < -0.2:
            add(-0.20, 0.10, "guilty", "he says she hurt him")
        # Insulted after failing; corrected; failing at a social moment.
        if kind == "insult" and self.failures_in_a_row > 0:
            add(-0.20, 0.10, "ashamed", "insulted after she failed")
        if m.get("correcting") and m.get("just_replied"):
            add(-0.08, 0.15, "embarrassed", "he corrected what she said")
        if kind == "reply_failed" and m.get("social_move"):
            add(-0.05, 0.10, "awkward", "she had nothing to say at a social moment")
        # Insulted again and again.
        self.insults_in_a_row = (getattr(self, "insults_in_a_row", 0) + 1) if kind == "insult" else (
            0 if kind in ("compliment", "thanks", "greeting") else getattr(self, "insults_in_a_row", 0))
        if self.insults_in_a_row >= 3:
            add(-0.10, 0.05, "contemptuous", "he keeps insulting her")
        # Not feeling safe for a while.
        if self.needs.safety < 0.45:
            add(-0.08, 0.15, "anxious", "she hasn't felt safe for a while")
        # Answering well.
        if kind == "answered_from_memory":
            add(0.06, 0.0, "satisfied", "she answered from what she knew")
        return felt

    def memory_feelings(self, good: float, days_ago: float, about_him: bool) -> List[Felt]:
        """A memory coming back: from long ago and good, nostalgia; while lonely
        and about him, longing."""
        felt: List[Felt] = []
        if days_ago > 1 and good > 0.2:
            felt.append(Felt(0.08, -0.05, "nostalgic", "a good memory from a while ago"))
        if about_him and self.needs.belonging < 0.5:
            felt.append(Felt(-0.05, 0.05, "longing", "remembering him while she's lonely"))
        return felt

    # ---- inside ---------------------------------------------------------
    def _change(self, need: str, change: float, reason: str) -> List[Felt]:
        if not hasattr(self.needs, need) or abs(change) < 1e-6:
            return []
        before = float(getattr(self.needs, need))
        after = max(0.0, min(1.0, before + change))
        setattr(self.needs, need, after)
        moved = after - before
        if abs(moved) < 1e-6:
            return []
        # An unmet need hurts more than a met one helps (people feel loss
        # more than gain), and a need already low hurts more when it drops.
        weight = 1.5 if moved < 0 else 1.0
        urgency = 1.0 + (0.5 if after < 0.3 and moved < 0 else 0.0)
        dv = moved * 1.2 * weight * urgency
        da = abs(moved) * (1.5 if need in ("competence", "stimulation", "safety") else 0.6)
        if need == "belonging" and moved < 0:
            da = -abs(moved) * 0.5  # loneliness is a quiet feeling
        feeling = FEELING_OF.get((need, 1 if moved > 0 else -1))
        return [Felt(dv, da, feeling, reason)]

    def state(self) -> Dict[str, Any]:
        return {
            "needs": {k: round(float(getattr(self.needs, k)), 3) for k in
                      ("belonging", "competence", "stimulation", "safety", "autonomy")},
            "attachment": {k: round(float(getattr(self.attachment, k)), 3) for k in
                           ("bond_strength", "hurt", "security")},
            "last_contact": self.last_contact,
            "failures_in_a_row": self.failures_in_a_row,
            "insults_in_a_row": getattr(self, "insults_in_a_row", 0),
            "last_feeling": self.last_feeling,
            "last_reason": self.last_reason,
        }

    def load(self, data: Dict[str, Any]) -> None:
        if not isinstance(data, dict):
            return
        self.last_contact = float(data.get("last_contact") or self.last_contact)
        self.last_time = float(data.get("last_time") or self.last_time)
        self.failures_in_a_row = int(data.get("failures_in_a_row") or 0)
        self.insults_in_a_row = int(data.get("insults_in_a_row") or 0)
        self.last_feeling = data.get("last_feeling")
        self.last_reason = str(data.get("last_reason") or "")


__all__ = ["InnerLife", "Felt", "EVENTS", "FEELING_OF"]
