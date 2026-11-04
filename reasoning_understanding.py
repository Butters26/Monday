"""Reasoning's understanding of what's going on, and what follows from it.

Matthew (Nov 3): reasoning is the explainer, not the balancer. It works out
what is happening, what follows and why, from everything the other lobes
know, and makes sure the other lobes understand it. It doesn't control
Emotion (emotion feels what it feels) and it doesn't decide what she does
(Executive Control does). Its written job: conclusions, explanations and
solutions; what the information supports, why something happened; what
follows kept apart from what's only a guess; uncertainty kept.

Each moment it puts together:
- what happened: what he did (Social Context's read), what he feels, what
  memory brought up, how new it is (Novelty), what she feels and why
  (Emotion), what's in focus (Attention);
- conclusions that follow from what she knows and the dictionary ("Rex is
  your dog, a dog is an animal, so Rex is an animal"), each with how sure
  and why; they're handed to memory as concluded (not told);
- explanations: why he feels what he feels ("because his dog died"), what
  changed ("he used to live in Ohio; now Denver"), whether her feeling has a
  reason in what's happening;
- what she isn't sure of (something new she knows nothing about).

It's announced as "understood" for any lobe that listens (Language, Emotion,
Executive Control...).
"""

from __future__ import annotations

from typing import Any, Callable, Dict, List, Optional

# The dictionary's own top groupings of things (its lexicographer files):
# what kind of thing a noun is, said as the group's own word.
_KIND_OF_FILE = {"noun.animal": "animal", "noun.person": "person", "noun.plant": "plant",
                 "noun.food": "food"}

_GOOD_MOVES = {"greeting", "thanks", "compliment", "check_in", "goodbye"}


def kind_of(noun: str) -> Optional[str]:
    """What group of things the dictionary puts a noun in ("dog" -> animal)."""
    try:
        from lexicon.oewn_offline import get_wordnet
        synsets = [x for x in get_wordnet().synsets(str(noun or "").casefold(), pos="n")
                   if any(str(l) == str(noun).casefold() for l in x.lemmas())]
    except Exception:
        return None
    if not synsets:
        return None
    kind = _KIND_OF_FILE.get(str(synsets[0].lexfile()))
    return kind if kind and kind != str(noun).casefold() else None


class Understanding:
    """Puts together what's going on in a moment, from what the lobes say."""

    def __init__(self, ask: Callable[[str, str, Dict[str, Any]], Dict[str, Any]]) -> None:
        self.ask = ask

    # ---- the moment -----------------------------------------------------------
    def understand(self, said: str, user_id: str, social: Dict[str, Any],
                   facts: List[Dict[str, Any]], emotion: Dict[str, Any],
                   novelty: Optional[float], focus: Optional[str]) -> Dict[str, Any]:
        happened: List[Dict[str, Any]] = []
        move = str(social.get("move") or "")
        meant = social.get("meant") if isinstance(social.get("meant"), dict) else {}
        if move:
            happened.append({"what": f"he made a social move: {move}", "from": "social context"})
        if meant.get("about") and meant.get("good") is not None:
            happened.append({"what": f"what he said is meant {'well' if float(meant['good']) > 0 else 'badly'}"
                             f" about {meant['about']}", "from": "social context",
                             "sure": "a reading of his words, not a fact"})
        his = social.get("his_feeling") if isinstance(social.get("his_feeling"), dict) else {}
        if his.get("words"):
            happened.append({"what": f"he feels {', '.join(map(str, his['words']))}", "from": "social context"})
        if facts:
            happened.append({"what": f"memory brought up {len(facts)} thing(s) she knows about this",
                             "from": "memory"})
        if focus:
            happened.append({"what": f"in focus: {focus}", "from": "attention"})
        conclusions = self.conclude(facts)
        explanations = self.explain(facts)
        feeling = self.her_feeling(emotion, move, meant)
        unsure: List[str] = []
        try:
            words_good, he_feels = float(meant.get("good") or 0.0), float(his.get("good") or 0.0)
        except (TypeError, ValueError):
            words_good, he_feels = 0.0, 0.0
        if words_good > 0.3 and he_feels < -0.3:
            unsure.append("his words sound good but he seems to feel bad; he may not mean them the way they "
                          "sound (sarcasm?), a guess")
        if novelty is not None and novelty > 0.7 and not facts:
            unsure.append("this is new to her and she knows nothing about it yet; anything she says about it is a guess")
        return {"said": said, "user_id": user_id, "happened": happened, "conclusions": conclusions,
                "explanations": explanations, "her_feeling": feeling, "unsure": unsure}

    # ---- what follows ----------------------------------------------------------
    def conclude(self, facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """New facts that follow from facts she has, with how sure and why."""
        out: List[Dict[str, Any]] = []
        known = {(str(f.get("subject")).casefold(), str(f.get("predicate")), str(f.get("object")).casefold())
                 for f in facts}

        def add(subject: str, predicate: str, obj: str, sure: float, why: str) -> None:
            key = (subject.casefold(), predicate, obj.casefold())
            if key in known or any((c["subject"].casefold(), c["predicate"], c["object"].casefold()) == key for c in out):
                return
            out.append({"subject": subject, "predicate": predicate, "object": obj, "sure": sure, "because": why})

        for f in facts:
            subject, predicate = str(f.get("subject") or ""), str(f.get("predicate") or "")
            obj = str(f.get("object") or "")
            if f.get("is_contradicted"):
                continue
            # "My dog is named Rex" is filed as (user, dog, Rex): Rex is a dog.
            if subject == "user" and obj[:1].isupper() and predicate.isalpha() \
                    and predicate not in ("is", "is_a", "name") and kind_of(predicate):
                add(obj, "is_a", predicate, 0.95, f"he said his {predicate} is {obj}")
                kind = kind_of(predicate)
                if kind and kind != "person":
                    add(obj, "is_a", kind, 0.9, f"{obj} is his {predicate}, and a {predicate} is an {kind}"
                        if kind[:1] in "aeiou" else f"{obj} is his {predicate}, and a {predicate} is a {kind}")
            # "Rex is a dog": a dog is an animal, so Rex is an animal.
            if predicate == "is_a" and obj and not obj[:1].isupper():
                kind = kind_of(obj.split()[-1])
                if kind and kind != obj.casefold():
                    add(subject, "is_a", kind, 0.9, f"{subject} is a {obj}, and the dictionary puts a {obj} with {kind}s")
        return out

    def explain(self, facts: List[Dict[str, Any]]) -> List[str]:
        """Why things are as they are, and what changed, from what she knows."""
        out: List[str] = []
        for f in facts:
            if str(f.get("because") or "").strip():
                out.append(f"{self._said(f)} because {f['because']}")
        by_action: Dict[tuple, List[Dict[str, Any]]] = {}
        for f in facts:
            by_action.setdefault((str(f.get("subject")), str(f.get("predicate"))), []).append(f)
        for (subject, predicate), group in by_action.items():
            past = [f for f in group if f.get("tense") == "past"]
            now = [f for f in group if not f.get("tense") and str(f.get("when_said") or "") in ("now", "")]
            if past and now and predicate.startswith("v:"):
                out.append(f"{subject} used to {predicate[2:].replace('@', ' ')} {past[0].get('object')}; "
                           f"now {now[0].get('object')}")
        return out

    def her_feeling(self, emotion: Dict[str, Any], move: str, meant: Dict[str, Any]) -> Dict[str, Any]:
        """What she feels, why (as Emotion says), and whether what's happening
        right now gives a reason for it. Reasoning doesn't change the feeling;
        it says what it makes of it."""
        name = str(emotion.get("monday_emotion") or emotion.get("emotion") or "").strip()
        reason = str(emotion.get("self_impact_reason") or "").strip()
        try:
            valence = float(emotion.get("valence") or 0.0)
        except (TypeError, ValueError):
            valence = 0.0
        if not name:
            return {}
        out: Dict[str, Any] = {"feeling": name, "because": reason or "(emotion didn't say)"}
        kind_now = move in _GOOD_MOVES or float(meant.get("good") or 0.0) > 0.2
        if valence < -0.3 and kind_now:
            out["fits_now"] = False
            out["note"] = (f"she feels {name}, but he is being kind right now; the feeling comes from "
                           f"before ({reason})" if reason else f"she feels {name}, but nothing bad is happening now")
        else:
            out["fits_now"] = True
        return out

    @staticmethod
    def _said(fact: Dict[str, Any]) -> str:
        predicate = str(fact.get("predicate") or "").replace("v:", "").replace("@", " ").replace("_", " ")
        return f"{fact.get('subject')} {predicate} {fact.get('object')}".replace(" (nothing)", "")


__all__ = ["Understanding", "kind_of"]
