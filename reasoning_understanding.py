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
                   novelty: Optional[float], focus: Optional[str],
                   patterns: Optional[Dict[str, Any]] = None,
                   reading: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        self._user_id = user_id
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
        changed = self.what_changed(said, user_id)
        likened = self.like_what_she_knows(reading or {}, facts, user_id)
        unsure += [x for x in likened if x not in unsure]
        shown = self.what_patterns_show(patterns or {})
        maybe_why = self.maybe_why(said, patterns or {}, facts)
        if maybe_why:
            unsure.append(maybe_why)
        problem = self.problem_in(reading or {}, facts)
        return {"said": said, "user_id": user_id, "happened": happened, "conclusions": conclusions,
                "explanations": explanations + changed + shown, "her_feeling": feeling, "unsure": unsure,
                **({"problem": problem} if problem else {})}

    # ---- what changed ---------------------------------------------------------
    def what_changed(self, said: str, user_id: str) -> List[str]:
        """Something he said before that a newer thing replaced (memory keeps
        the old one as history): "his dog was Rex; now he says Max". It's
        said as a change, not decided which is right."""
        body = self.ask("notus", "get_contradictions", {"statement": said, "user_id": user_id}) or {}
        out: List[str] = []
        current = (self.ask("notus", "query_facts", {"query": said, "user_id": user_id, "limit": 20}) or {}).get("facts") or []
        for c in (body.get("contradictions") or [])[:3]:
            # What took its place: the current fact about the same thing.
            new_obj = next((str(f.get("object")) for f in current
                            if str(f.get("subject")) == str(c.get("subject"))
                            and str(f.get("predicate")) == str(c.get("predicate"))
                            and str(f.get("object")) != str(c.get("object"))), None)
            subject = str(c.get("subject") or "")
            subject = "his" if subject == "user" else subject.replace("user's", "his")
            what = f"{subject} {str(c.get('predicate') or '').replace('v:', '').replace('_', ' ')}".strip()
            if new_obj:
                out.append(f"{what} was {c.get('object')} before; now it's {new_obj} (he changed it or corrected it)")
                old = str(c.get("object") or "")
                if old[:1].isupper():
                    # What she concluded from the old one no longer follows.
                    out.append(f"what she concluded about {old} from that (that {old} is his "
                               f"{str(c.get('predicate') or '').replace('_', ' ')}) no longer follows")
            else:
                out.append(f"he said {what} {c.get('object')} before, and later something that doesn't agree")
        return out

    # ---- something new: what it's like ----------------------------------------
    def like_what_she_knows(self, reading: Dict[str, Any], facts: List[Dict[str, Any]], user_id: str) -> List[str]:
        """Something she knows nothing about ("my hamster"): what the dictionary
        says it is, and what she knows about others of that kind ("a hamster is
        an animal, like your dog"). Only a guess that it's like them."""
        out: List[str] = []
        # What she already knows something about: things facts are about (not
        # just the line he said now, which memory has already filed).
        known_words = " ".join(f"{f.get('subject')} {f.get('predicate')}" for f in facts
                               if str(f.get("predicate")) not in ("v:get", "v:have", "v:buy")).casefold()
        for token in reading.get("tokens") or []:
            if token.get("kind") != "noun":
                continue
            noun = str(token.get("lemma") or "").casefold()
            if not noun or noun in known_words:
                continue
            kind = kind_of(noun)
            if not kind:
                continue
            same = self.ask("notus", "query_facts", {"query": kind, "user_id": user_id, "limit": 10}) or {}
            others = [str(f.get("subject")) for f in same.get("facts") or []
                      if str(f.get("predicate")) == "is_a" and str(f.get("object")).casefold() == kind
                      and noun not in str(f.get("subject")).casefold()]
            if others:
                article = "an" if kind[:1] in "aeiou" else "a"
                out.append(f"she doesn't know {noun}s yet; a {noun} is {article} {kind}, like {others[0]}, so it may be "
                           f"like {others[0]} in some ways (a guess)")
        return out

    @staticmethod
    def maybe_why(said: str, patterns: Dict[str, Any], facts: List[Dict[str, Any]]) -> Optional[str]:
        """"Why am I tired?" with no reason he ever gave: what keeps coming up
        with it is a possible reason, said as a guess, never as the cause."""
        words = [w.strip("?.!,").casefold() for w in said.split()]
        if not words or words[0] != "why" or any(str(f.get("because") or "").strip() for f in facts):
            return None
        if isinstance(patterns.get("significant_patterns"), dict):
            patterns = patterns["significant_patterns"]
        for p in patterns.get("strong_co_occurrences") or []:
            items = [str(i).casefold() for i in p.get("items") or []]
            if len(items) == 2 and (items[0] in words) != (items[1] in words):
                asked, other = (items[0], items[1]) if items[0] in words else (items[1], items[0])
                return (f"he never said why; {asked} keeps coming up with {other} ({p.get('count')} times), "
                        f"so maybe it's because of {other}, a guess, not shown")
        return None

    # ---- what patterns show ----------------------------------------------------
    @staticmethod
    def what_patterns_show(patterns: Dict[str, Any]) -> List[str]:
        """What Pattern Recognition found, and what it does and doesn't show:
        things coming up together isn't one causing the other."""
        out: List[str] = []
        if isinstance(patterns.get("significant_patterns"), dict):
            patterns = patterns["significant_patterns"]  # as Thalamus hands it over
        for p in (patterns.get("strong_co_occurrences") or [])[:3]:
            items = [str(i) for i in p.get("items") or []]
            if len(items) == 2:
                out.append(f"{items[0]} and {items[1]} keep coming up together ({p.get('count')} times); "
                           "that alone doesn't show one causes the other")
        for p in (patterns.get("reliable_sequences") or [])[:2]:
            steps = [str(x) for x in p.get("steps") or []]
            if len(steps) >= 2:
                out.append(f"{' then '.join(steps)} keeps happening in that order; a guess that it will again")
        for c in (patterns.get("contradictions") or [])[:2]:
            out.append(f"he said things that don't agree: {c}")
        return out

    # ---- problems and how they were solved -------------------------------------
    def problem_in(self, reading: Dict[str, Any], facts: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """"My car won't start", "I can't find my keys": something he can't get
        to happen. What solved something like it before is a possible way, a
        guess; with nothing like it before she doesn't know a way yet."""
        clause = (reading.get("clauses") or [{}])[0]
        negative = (clause.get("qualifiers") or {}).get("polarity") == "negative"
        modal = str(reading.get("modal") or "")
        tokens = [str(t.get("surface") or "").casefold() for t in reading.get("tokens") or []]
        if not negative or not (modal in ("can", "could", "would") or "will" in tokens or "wo" in tokens):
            return None
        verb = str(clause.get("predicate_surface") or "")
        if not verb:
            return None
        roles = clause.get("roles") or {}
        mentions = {m.get("mention_id"): m for m in reading.get("mentions") or []}
        who = str((mentions.get(roles.get("agent") or roles.get("theme")) or {}).get("surface") or "")
        thing = str((mentions.get(roles.get("patient") or roles.get("theme")) or {}).get("surface") or who)
        head = thing.split()[-1].casefold() if thing else ""
        if head:
            # What she knows about the thing itself, ways that fixed it included.
            more = self.ask("notus", "query_facts", {"query": head, "user_id": getattr(self, "_user_id", "default"),
                                                      "limit": 20}) or {}
            facts = list(facts) + [f for f in more.get("facts") or [] if isinstance(f, dict)]
        ways = [f for f in facts if str(f.get("predicate") or "") == "solved_by"
                and head and head in str(f.get("subject") or "").casefold()]
        out: Dict[str, Any] = {"what": f"{who or 'something'} can't {verb}", "thing": thing}
        if ways:
            out["maybe"] = [f"last time, {w.get('object')} fixed {w.get('subject')} (it may work again)" for w in ways]
        else:
            out["unsure"] = "she doesn't know a way to fix this yet; she'd need to know more or be told"
        return out

    def solution_in(self, reading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """"I fixed my car by charging the battery": a way that solved
        something, kept so it can be suggested next time."""
        clause = (reading.get("clauses") or [{}])[0]
        verb = str(clause.get("predicate_surface") or "")
        raw = str(reading.get("raw_text") or "")
        if " by " not in f" {raw.casefold()} " or not verb:
            return None
        try:
            from lexicon.oewn_offline import get_wordnet
            wn = get_wordnet()
            targets = {x.id for w in ("repair", "solve", "fix") for x in wn.synsets(w, pos="v")}
            frontier = list(wn.synsets(verb, pos="v"))[:3]
            fixes = False
            for _ in range(3):
                if {x.id for x in frontier} & targets:
                    fixes = True
                    break
                frontier = [h for x in frontier for h in x.hypernyms()]
        except Exception:
            return None
        if not fixes:
            return None
        roles = clause.get("roles") or {}
        mentions = {m.get("mention_id"): m for m in reading.get("mentions") or []}
        thing = str((mentions.get(roles.get("patient") or roles.get("theme")) or {}).get("surface") or "")
        how = raw[raw.casefold().index(" by ") + 4:].strip(" .!")
        thing = thing.split(" by ")[0].strip()  # "my car by charging..." -> "my car"
        words = thing.split()
        if words and words[0].casefold() in ("my", "our"):
            thing = "user's " + " ".join(words[1:])  # filed the way memory files his things
        if not thing or not how:
            return None
        return {"subject": thing, "predicate": "solved_by", "object": how, "sure": 0.8,
                "because": f"he said: {raw.strip()}"}

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
