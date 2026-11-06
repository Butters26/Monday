"""Reasoning's general engine: putting what she knows together into new things.

Matthew (Nov 6): reasoning should reason, about anything, not only the few
kinds of conclusions written by hand. So instead of a rule per topic, a few
general forms of reasoning that work on whatever she knows:

1. What's true of a kind is probably true of each one of it ("dogs bark",
   "Rex is a dog" -> Rex probably barks). The nearest kind wins, so what's
   said about penguins beats what's said about birds; what's said about the
   one itself beats both. Kinds come from what he said ("a penguin is a
   bird") and from the dictionary (a dog is a canine, a mammal, an animal).
2. Comparisons chain ("Max is older than Ben", "Ben is older than Lily" ->
   Max is older than Lily).
3. Opposites: what the dictionary gives as the opposite isn't also true
   ("Ben is tall" -> Ben isn't short).
4. How relations between people behave comes from her beliefs file
   (reasoning_beliefs.txt in her runtime folder, which Matthew can edit):
   whether a relation is shared (two of someone's siblings are each other's)
   or passed on (someone's parent is their siblings' parent too).
5. Rules he gives ("if it rains we stay home") are used when their first part
   comes true (in reasoning_understanding.py).

Every conclusion keeps how sure it is: never surer than what it rests on,
less for each step. What he told her always beats what she concluded, and a
correction ("penguins can't fly") stops a conclusion from being made.
Conclusions chain: one conclusion can lead to the next, a few steps deep.
"""

from __future__ import annotations

import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Set, Tuple

_ARTICLES = ("a ", "an ", "the ")
_BELIEF = re.compile(r"^\s*(?P<kind>[a-z ]+?)\s*:\s*(?P<how>shared|passes to (?P<to>[a-z ]+?))\s*"
                     r"(?:\((?P<note>[^)]*)\))?\s*(?:\(sure (?P<sure>[0-9.]+)\))?\s*$", re.IGNORECASE)

# Placeholder lines until Matthew writes his own (like social_beliefs.txt):
# how relations between people behave. Each can be edited or removed.
PLACEHOLDER_BELIEFS = """# How relations between people behave. Edit freely.
# "<kind>: shared" -> two of someone's <kind>s are each other's <kind>s.
# "<kind>: passes to <other kind>" -> someone's <kind> is also the <kind> of their <other kind>s.
sibling: shared (two of someone's siblings are each other's siblings) (sure 0.95)
parent: passes to sibling (someone's parent is their siblings' parent too) (sure 0.9)
"""


def _wn():
    from lexicon.oewn_offline import get_wordnet
    return get_wordnet()


def _ordinary(word: str, pos: str = "n") -> list:
    """The word's meanings in small letters (not a name spelled the same)."""
    try:
        return [x for x in _wn().synsets(word, pos=pos) if any(str(l) == word for l in x.lemmas())]
    except Exception:
        return []


def base_noun(words: str) -> str:
    """"a penguin" -> penguin, "dogs" -> dog, "user's dog" stays."""
    w = str(words or "").strip().casefold()
    for article in _ARTICLES:
        if w.startswith(article):
            w = w[len(article):]
    if " " in w or "'" in w or not w.isalpha():
        return w
    if _ordinary(w):
        return w
    for cut in ("es", "s"):
        if w.endswith(cut) and _ordinary(w[: -len(cut)]):
            return w[: -len(cut)]
    return w


def is_kind_word(subject: str) -> bool:
    """"dogs", "a penguin", "birds": a kind of thing (a word the dictionary
    has as a thing), not a name or someone's own ("Rex", "user's dog")."""
    s = str(subject or "").strip()
    if not s or s[:1].isupper() or "'" in s or s.casefold() in ("user", "monday", "i", "you"):
        return False
    return bool(_ordinary(base_noun(s)))


def dictionary_kinds(noun: str, depth: int = 6) -> List[str]:
    """What the dictionary says a thing is, nearest first (dog -> canine,
    carnivore, placental, mammal, ... animal)."""
    out: List[str] = []
    frontier = _ordinary(noun)[:1]
    for _ in range(depth):
        frontier = [h for x in frontier for h in x.hypernyms()]
        for x in frontier:
            for lemma in x.lemmas()[:2]:
                name = str(lemma)
                if name.islower() and name not in out:
                    out.append(name)
    return out


def opposites(adjective: str) -> List[str]:
    """The dictionary's opposites of a describing word (tall -> short)."""
    out: List[str] = []
    try:
        for x in _wn().synsets(adjective, pos="a")[:2]:
            for sense in x.senses():
                if str(sense.word().lemma()) != adjective:
                    continue
                for rel in sense.get_related("antonym"):
                    word = str(rel.word().lemma())
                    if word not in out:
                        out.append(word)
    except Exception:
        return []
    return out


class RelationBeliefs:
    """Her beliefs about how relations between people behave (editable)."""

    def __init__(self, path: Optional[str]) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.beliefs: List[Dict[str, Any]] = []
        self.load()

    def load(self) -> None:
        text = PLACEHOLDER_BELIEFS
        if self.path:
            p = Path(self.path)
            try:
                if not p.exists():
                    p.write_text(PLACEHOLDER_BELIEFS, encoding="utf-8")
                text = p.read_text(encoding="utf-8")
            except Exception as error:
                print(f"⚠️  Reasoning: couldn't read her beliefs about relations ({error}); using the placeholders")
        beliefs = []
        for line in text.splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            m = _BELIEF.match(line)
            if not m:
                print(f"⚠️  Reasoning: didn't understand this belief line, skipped: {line.strip()}")
                continue
            beliefs.append({"kind": m.group("kind").strip().casefold(),
                            "how": "shared" if m.group("how").casefold() == "shared" else "passes",
                            "to": (m.group("to") or "").strip().casefold(),
                            "sure": float(m.group("sure") or 0.9)})
        with self.lock:
            self.beliefs = beliefs


class Engine:
    """Puts facts together into new ones, by a few general forms of reasoning."""

    MAX_ROUNDS = 3

    def __init__(self, relation_kind: Callable[[str], Optional[str]], beliefs: RelationBeliefs) -> None:
        self.relation_kind = relation_kind
        self.beliefs = beliefs

    @staticmethod
    def _sure(fact: Dict[str, Any]) -> float:
        for key in ("sure", "confidence"):
            try:
                value = float(fact.get(key))
                if 0.0 < value <= 1.0:
                    return value
            except (TypeError, ValueError):
                continue
        return 0.8

    @staticmethod
    def _who(subject: Any) -> str:
        """"a penguin", "penguins" and "penguin" are the same thing being talked about."""
        s = str(subject or "")
        return (base_noun(s) if is_kind_word(s) else s).casefold()

    @classmethod
    def _key(cls, fact: Dict[str, Any]) -> Tuple[str, str, str, str]:
        return (cls._who(fact.get("subject")), str(fact.get("predicate") or ""),
                str(fact.get("object") or "").casefold(), cls._meaning_value(fact.get("value")))

    @staticmethod
    def _meaning_value(value: Any) -> str:
        """"said:flies" only keeps how he worded it; it doesn't change what it means."""
        v = str(value or "")
        return "" if v.startswith("said:") else v

    @staticmethod
    def _negated(predicate: str) -> str:
        return predicate[4:] if predicate.startswith("not_") else "not_" + predicate

    def infer(self, facts: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        known: List[Dict[str, Any]] = [dict(f) for f in facts if isinstance(f, dict) and not f.get("is_contradicted")]
        seen = {self._key(f) for f in known}
        told = {self._key(f) for f in known if not str(f.get("held_by") or "").startswith("concluded")}
        out: List[Dict[str, Any]] = []
        for _ in range(self.MAX_ROUNDS):
            new = []
            for c in self._names(known) + self._kinds(known) + self._comparisons(known) + self._opposites(known) \
                    + self._relations(known):
                k = self._key(c)
                negated = (k[0], self._negated(k[1]), k[2], k[3])
                if k in seen or negated in told:
                    continue  # already known, or he said otherwise
                seen.add(k)
                new.append(c)
            if not new:
                break
            out += new
            known += new
        return out

    def overruled(self, facts: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Her earlier guesses that what he has told her since says are wrong."""
        known = [f for f in facts if isinstance(f, dict) and not f.get("is_contradicted")]
        told = {self._key(f) for f in known if not str(f.get("held_by") or "").startswith("concluded")}
        out = []
        for f in known:
            if str(f.get("held_by") or "").startswith("concluded"):
                k = self._key(f)
                if (k[0], self._negated(k[1]), k[2], k[3]) in told:
                    out.append(f)
        return out

    # 0. a name for one of someone's things ------------------------------------
    def _names(self, known: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """"His dog is Rex" (filed as user / dog / Rex): Rex is a dog."""
        out = []
        for f in known:
            predicate, obj = str(f.get("predicate") or ""), str(f.get("object") or "")
            if obj[:1].isupper() and predicate.isalpha() and predicate not in ("is", "is_a", "then") \
                    and _ordinary(predicate) and not self.relation_kind(predicate):
                # (A relation isn't a kind: "his sister is Lily" says who she is to him.)
                whose = "his" if str(f.get("subject")) == "user" else f"{f.get('subject')}'s"
                out.append({"subject": obj, "predicate": "is_a", "object": predicate,
                            "sure": round(self._sure(f) * 0.98, 2),
                            "because": f"{obj} is {whose} {predicate}"})
        return out

    # 1. what's true of a kind ----------------------------------------------
    def _kinds(self, known: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        is_a: Dict[str, List[Tuple[str, float]]] = {}
        about_kind: Dict[str, List[Dict[str, Any]]] = {}
        for f in known:
            subject, predicate = str(f.get("subject") or ""), str(f.get("predicate") or "")
            if predicate == "is_a":
                one = base_noun(subject) if is_kind_word(subject) else subject
                is_a.setdefault(one, []).append((base_noun(str(f.get("object") or "")), self._sure(f)))
            elif is_kind_word(subject) and predicate not in ("then", "solved_by"):
                about_kind.setdefault(base_noun(subject), []).append(f)
        out = []
        for one, direct in is_a.items():
            # Its kinds, nearest first: what he said, then what the dictionary says.
            chain: List[Tuple[str, float, str]] = []
            for kind, sure in direct:
                chain.append((kind, sure, f"{one} is a {kind}"))
                for further in is_a.get(kind, []):
                    chain.append((further[0], sure * further[1], f"{one} is a {kind}, and a {kind} is a {further[0]}"))
                for n, k in enumerate(dictionary_kinds(kind)):
                    chain.append((k, sure * max(0.5, 0.95 - 0.03 * n), f"{one} is a {kind}, and the dictionary "
                                                                         f"puts a {kind} with {k}s"))
            decided: Set[Tuple[str, str]] = set()
            own = {(str(f.get("predicate")).replace("not_", ""), self._meaning_value(f.get("value")))
                   for f in known if self._who(f.get("subject")) == self._who(one)}
            for kind, sure, why in chain:
                for f in about_kind.get(kind, []):
                    predicate = str(f.get("predicate") or "")
                    plain = (predicate.replace("not_", ""), self._meaning_value(f.get("value")))
                    if plain in own or plain in decided:
                        continue  # what's said about it, or a nearer kind, already decides
                    decided.add(plain)
                    said = "can't" if predicate.startswith("not_") and f.get("modal") == "can" else \
                        "doesn't" if predicate.startswith("not_") else (f.get("modal") or "")
                    out.append({"subject": one, "predicate": predicate, "object": f.get("object"),
                                "value": f.get("value"), "modal": f.get("modal"),
                                "sure": round(sure * self._sure(f) * 0.85, 2),
                                "because": f"{why}; {f.get('subject')} {said} "
                                           f"{predicate.replace('not_', '').replace('v:', '').replace('_', ' ')}"
                                           .replace("  ", " ").strip() + " (true of most, maybe not all)"})
        return out

    # 2. comparisons chain ---------------------------------------------------
    def _comparisons(self, known: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        more: Dict[Tuple[str, str], List[Tuple[str, float]]] = {}
        for f in known:
            value = str(f.get("value") or "")
            if value.startswith("than:"):
                more.setdefault((str(f.get("subject")), str(f.get("object"))), []).append((value[5:], self._sure(f)))
        out = []
        for (a, word), list_b in more.items():
            for b, s1 in list_b:
                for c, s2 in more.get((b, word), []):
                    if c != a:
                        out.append({"subject": a, "predicate": "is", "object": word, "value": f"than:{c}",
                                    "sure": round(min(s1, s2) * 0.95, 2),
                                    "because": f"{a} is {word} than {b}, and {b} is {word} than {c}"})
        return out

    # 3. opposites -----------------------------------------------------------
    def _opposites(self, known: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = []
        for f in known:
            if str(f.get("predicate")) != "is" or f.get("value"):
                continue
            adjective = str(f.get("object") or "").casefold()
            if not adjective.isalpha():
                continue
            for other in opposites(adjective)[:1]:
                out.append({"subject": f.get("subject"), "predicate": "not_is", "object": other,
                            "sure": round(self._sure(f) * 0.9, 2),
                            "because": f"{f.get('subject')} is {adjective}, and {other} is its opposite"})
        return out

    # 4. relations between people, as her beliefs say they behave -------------
    def _relations(self, known: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        relatives = [(str(f.get("subject")), str(f.get("predicate")), str(f.get("object")), self._sure(f))
                     for f in known if str(f.get("object") or "")[:1].isupper()
                     and str(f.get("predicate") or "").isalpha() and self.relation_kind(str(f.get("predicate")))]
        out = []
        for belief in self.beliefs.beliefs:
            for owner in {r[0] for r in relatives}:
                whose = "his" if owner == "user" else f"{owner}'s"
                mine = [r for r in relatives if r[0] == owner and self.relation_kind(r[1]) == belief["kind"]]
                if belief["how"] == "shared":
                    for a in mine:
                        for b in mine:
                            if a[2] != b[2]:
                                out.append({"subject": b[2], "predicate": a[1], "object": a[2],
                                            "sure": round(min(a[3], b[3]) * belief["sure"], 2),
                                            "because": f"{a[2]} and {b[2]} are both {whose} {belief['kind']}s"})
                else:
                    others = [r for r in relatives if r[0] == owner and self.relation_kind(r[1]) == belief["to"]]
                    for a in mine:
                        for o in others:
                            out.append({"subject": o[2], "predicate": a[1], "object": a[2],
                                        "sure": round(min(a[3], o[3]) * belief["sure"], 2),
                                        "because": f"{a[2]} is {whose} {a[1]} and {o[2]} is {whose} {o[1]}"})
        return out


__all__ = ["Engine", "RelationBeliefs", "PLACEHOLDER_BELIEFS", "dictionary_kinds", "opposites", "base_noun",
           "is_kind_word"]
