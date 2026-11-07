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
6. Amounts: "I have 3 dogs", "I got 2 more" -> probably 5 dogs now; who has
   more of something. Which words add and which take away comes from her
   amounts file (reasoning_amounts.txt, editable) and the dictionary's
   opposites (more -> fewer, buy -> sell); numbers written as words come from
   the dictionary (three -> 3).
6b. Measures: "Max is 10 years old", "Lily is 7 years old" -> Max is 3 years
   older than Lily (the -er word is checked against the dictionary).
7. Time order chains ("breakfast before work", "work before the gym" ->
   breakfast before the gym).
8. Why, more than one step: "tired because I didn't sleep", "didn't sleep
   because I drank coffee" -> the coffee may be part of why he's tired. "If"
   rules chain the same way (rain -> wet grass -> muddy dog).

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


# How amounts change, until Matthew writes his own. Each can be edited or removed.
PLACEHOLDER_AMOUNTS = """# How amounts change. Edit freely.
# "<word>: says how many" -> "I have 3 dogs" says how many dogs he has.
# "<word>: adds" -> "I got 2 dogs", "2 more dogs" adds to how many.
# "<word>: takes away" -> "I sold 2 dogs" takes away.
# A word the dictionary gives as the opposite of one that adds takes away
# (more -> fewer, buy -> sell, find -> lose), so those needn't be written.
have: says how many
more: adds
get: adds
buy: adds
find: adds
"""
_AMOUNT = re.compile(r"^\s*(?P<word>[a-z ]+?)\s*:\s*(?P<how>says how many|adds|takes away)\s*$", re.IGNORECASE)


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


def opposites(adjective: str, pos: str = "a", senses: Optional[int] = None) -> List[str]:
    """The dictionary's opposites of a word (tall -> short, buy -> sell).
    senses=1: only its main meaning ("green" the color has none; green as in
    unripe isn't what he meant)."""
    out: List[str] = []
    try:
        for x in _wn().synsets(adjective, pos=pos)[:senses or (3 if pos != "a" else 2)]:
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


def _forms(word: str, pos: str) -> List[str]:
    """The dictionary's own other forms of a word (foot -> feet, big -> bigger, biggest)."""
    try:
        from lexicon.oewn_offline import get_wordnet
        for entry in get_wordnet().words(word, pos=pos):
            if str(entry.lemma()).casefold() == word.casefold():
                return [str(f) for f in entry.forms() if str(f).casefold() != word.casefold()]
    except Exception:
        pass
    return []


def _syllables(word: str) -> int:
    return max(1, len(re.findall(r"[aeiouy]+", word.casefold().rstrip("e"))))


def words_plural(noun: str) -> str:
    """year -> years, inch -> inches, foot -> feet (the dictionary's own form if it lists one)."""
    w = noun.casefold()
    listed = _forms(w, "n")
    if listed:
        return listed[0]
    if re.search(r"(s|x|z|ch|sh)$", w):
        return w + "es"
    if re.search(r"[^aeiou]y$", w):
        return w[:-1] + "ies"
    return w + "s"


def singular(noun: str) -> str:
    """years -> year, feet -> foot."""
    w = noun.casefold()
    try:
        from lexicon.oewn_offline import lemma_and_pos_candidates
        other = [c["lemma"] for c in lemma_and_pos_candidates(w) if c.get("pos") == "n" and c["lemma"] != w]
        if other:
            return other[0]
    except Exception:
        pass
    return w


def number_in(word: str) -> Optional[int]:
    """"3" -> 3, "three" -> 3, "dozen" -> 12: the dictionary writes each
    number word with its digits."""
    w = str(word or "").strip().casefold()
    if w.isdigit():
        return int(w)
    try:
        for x in _wn().synsets(w):
            for lemma in x.lemmas():
                if str(lemma).isdigit():
                    return int(str(lemma))
    except Exception:
        return None
    return None


def word_lemmas(text: str) -> Set[str]:
    """The dictionary forms of the words ("drank coffee" -> drink, coffee)."""
    out: Set[str] = set()
    for w in re.findall(r"[a-z']+", str(text or "").casefold().replace("_", " ")):
        if w in ("not", "n't", "no", "never") or w.endswith("n't"):
            continue
        try:
            from lexicon.oewn_offline import lemma_and_pos_candidates
            forms = lemma_and_pos_candidates(w)
        except Exception:
            forms = []
        verbs = [f["lemma"] for f in forms if f.get("pos") == "v"]
        out.add((verbs or [f["lemma"] for f in forms] or [w])[0].casefold())
    return out


def is_negative(text: str) -> bool:
    words = re.findall(r"[a-z']+", str(text or "").casefold())
    return any(w in ("not", "no", "never") or w.endswith("n't") for w in words)


def same_happening(a: Set[str], b: Set[str]) -> float:
    """How much two happenings are the same, by their words (0..1)."""
    if not a or not b:
        return 0.0
    # The words of the shorter one all in the longer one ("didn't sleep" in
    # "I did not sleep") count fully; less shared, less the same.
    return len(a & b) / min(len(a), len(b)) * (0.6 + 0.4 * len(a & b) / len(a | b))


class AmountBeliefs:
    """Her beliefs about which words say, add to or take away from how many (editable)."""

    def __init__(self, path: Optional[str]) -> None:
        self.how: Dict[str, str] = {}
        text = PLACEHOLDER_AMOUNTS
        if path:
            p = Path(path)
            try:
                if not p.exists():
                    p.write_text(PLACEHOLDER_AMOUNTS, encoding="utf-8")
                text = p.read_text(encoding="utf-8")
            except Exception as error:
                print(f"⚠️  Reasoning: couldn't read her beliefs about amounts ({error}); using the placeholders")
        for line in text.splitlines():
            if not line.strip() or line.strip().startswith("#"):
                continue
            m = _AMOUNT.match(line)
            if not m:
                print(f"⚠️  Reasoning: didn't understand this amounts line, skipped: {line.strip()}")
                continue
            self.how[m.group("word").strip().casefold()] = m.group("how").casefold()

    def of(self, word: str, pos: str) -> str:
        """"says how many", "adds", "takes away", or "" for a word that doesn't change amounts."""
        w = str(word or "").casefold()
        if w in self.how:
            return self.how[w]
        for adds in [k for k, v in self.how.items() if v == "adds"]:
            if w in opposites(adds, pos) or adds in opposites(w, pos):
                return "takes away"
        return ""


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


def _is_person(word: str) -> bool:
    """"Tom is Lily's son" says who Tom is to Lily, not what kind of thing he is."""
    try:
        from reasoning_understanding import is_person_word
        return is_person_word(word)
    except Exception:
        return False


class Engine:
    """Puts facts together into new ones, by a few general forms of reasoning."""

    MAX_ROUNDS = 3

    def __init__(self, relation_kind: Callable[[str], Optional[str]], beliefs: RelationBeliefs,
                 amounts: Optional[AmountBeliefs] = None) -> None:
        self.relation_kind = relation_kind
        self.beliefs = beliefs
        self.amounts = amounts or AmountBeliefs(None)

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
        return "" if v.startswith(("said:", "via:")) else v

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
                    + self._relations(known) + self._amounts(known) + self._measures(known) + self._order(known) + self._why(known):
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
                    and _ordinary(predicate) and not self.relation_kind(predicate) and not _is_person(predicate) \
                    and predicate != "name" and not predicate.endswith("_name"):
                # ("My name is Matthew": Matthew is his name, not a kind of thing.)
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
            for other in opposites(adjective, senses=1)[:1]:
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
            for owner in {r[0].casefold() for r in relatives}:
                # ("lily" and "Lily" are the same person.)
                shown = next((r[0] for r in relatives if r[0].casefold() == owner and r[0][:1].isupper()), owner)
                whose = "his" if owner == "user" else f"{shown}'s"
                mine = [r for r in relatives if r[0].casefold() == owner and self.relation_kind(r[1]) == belief["kind"]]
                if belief["how"] == "shared":
                    for a in mine:
                        for b in mine:
                            if a[2] != b[2]:
                                out.append({"subject": b[2], "predicate": a[1], "object": a[2],
                                            "sure": round(min(a[3], b[3]) * belief["sure"], 2),
                                            "because": f"{a[2]} and {b[2]} are both {whose} {belief['kind']}s"})
                else:
                    others = [r for r in relatives if r[0].casefold() == owner and self.relation_kind(r[1]) == belief["to"]]
                    for a in mine:
                        for o in others:
                            out.append({"subject": o[2], "predicate": a[1], "object": a[2],
                                        "sure": round(min(a[3], o[3]) * belief["sure"], 2),
                                        "because": f"{a[2]} is {whose} {a[1]} and {o[2]} is {whose} {o[1]}"})
        return out


    # 6. amounts --------------------------------------------------------------
    @staticmethod
    def _told_in_order(known: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        told = [f for f in known if not str(f.get("held_by") or "").startswith("concluded")
                and isinstance(f.get("id"), int)]
        return sorted(told, key=lambda f: f["id"])

    def _amounts(self, known: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """"I have 3 dogs", then "I got 2 more dogs" -> probably 5 dogs now.
        Who has more: "I have 3 dogs", "Ben has 5 dogs" -> Ben has 2 more."""
        story: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for f in self._told_in_order(known):
            predicate = str(f.get("predicate") or "")
            if not predicate.startswith("v:"):
                continue
            verb = predicate[2:].split("@", 1)[0]
            words = str(f.get("object") or "").split()
            if len(words) < 2:
                continue
            n = number_in(words[0])
            if n is None:
                continue
            rest = words[1:]
            how = ""
            if rest and self.amounts.of(rest[0], "a"):
                how, rest = self.amounts.of(rest[0], "a"), rest[1:]  # "2 more dogs"
            if not rest:
                continue
            how = how if how in ("adds", "takes away") else (self.amounts.of(verb, "v") or how)
            noun = base_noun(" ".join(rest))
            key = (str(f.get("subject") or ""), noun)
            said_verb = str(f.get("value") or "")[5:] if str(f.get("value") or "").startswith("said:") else verb
            line = story.setdefault(key, {"total": None, "said": [], "plural": " ".join(rest), "sure": 1.0,
                                          "changed": False})
            if how == "says how many":
                line.update(total=n, said=[f"{'had' if verb == 'have' else said_verb} {' '.join(words)}"],
                            changed=False)
                if n != 1:
                    line["plural"] = " ".join(rest)
            elif how in ("adds", "takes away") and line["total"] is not None:
                line["total"] += n if how == "adds" else -n
                line["said"].append(f"{said_verb} {' '.join(words)}")
                line["changed"] = True
            else:
                continue
            line["sure"] *= self._sure(f)
        out = []
        for (who, noun), line in story.items():
            if line["changed"] and line["total"] is not None and line["total"] >= 0:
                total = line["total"]
                out.append({"subject": who, "predicate": "v:have",
                            "object": f"{total} {line['plural'] if total != 1 else noun}",
                            "sure": round(line["sure"] * 0.9, 2),
                            "keep": False,  # worked out again each time, from what he said
                            "because": ("he" if who == "user" else who) + " " + ", then ".join(line["said"])
                                       + f", so {total} now, unless some were missed"})
        owners: Dict[str, List[Tuple[str, int, float, str]]] = {}
        for (who, noun), line in story.items():
            if line["total"] is not None:
                owners.setdefault(noun, []).append((who, line["total"], line["sure"], line["plural"]))
        for noun, have in owners.items():
            for a in have:
                for b in have:
                    if a[0] != b[0] and a[1] > b[1]:
                        name = lambda w: "he" if w == "user" else w
                        out.append({"subject": a[0], "predicate": "v:have",
                                    "object": f"{a[1] - b[1]} more {a[3] if a[1] - b[1] != 1 else noun}",
                                    "value": f"than:{b[0]}", "sure": round(min(a[2], b[2]) * 0.9, 2),
                                    "because": f"{name(a[0])} has {a[1]} and {name(b[0])} has {b[1]}"})
        return out

    @staticmethod
    def _more(describing: str) -> str:
        """old -> older, big -> bigger, good -> better, careful -> more careful
        (the dictionary's own form if it lists one)."""
        w = describing.casefold()
        listed = [f for f in _forms(w, "a") if not f.endswith("st")]
        if listed:
            return listed[0]
        if _syllables(w) == 1:
            if re.search(r"[^aeiou][aeiou][^aeiouwxy]$", w):
                return w + w[-1] + "er"
            return w + ("r" if w.endswith("e") else "er")
        if _syllables(w) == 2 and w.endswith("y"):
            return w[:-1] + "ier"
        return f"more {w}"

    def _measures(self, known: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """"Max is 10 years old", "Lily is 7 years old" -> Max is 3 years older than Lily."""
        measured: Dict[Tuple[str, str], List[Tuple[str, int, float]]] = {}
        for f in self._told_in_order(known):
            if str(f.get("predicate") or "") != "is":
                continue
            words = str(f.get("object") or "").split()
            if len(words) != 3:
                continue
            n = number_in(words[0])
            if n is None:
                continue
            unit, describing = singular(words[1]), words[2].casefold()
            mine = measured.setdefault((unit, describing), [])
            mine[:] = [m for m in mine if m[0] != str(f.get("subject"))]  # the latest he said
            mine.append((str(f.get("subject")), n, self._sure(f)))
        out = []
        for (unit, describing), them in measured.items():
            for a in them:
                for b in them:
                    if a[0] != b[0] and a[1] > b[1]:
                        d = a[1] - b[1]
                        units = unit if d == 1 else (words_plural(unit))
                        out.append({"subject": a[0], "predicate": "is",
                                    "object": f"{d} {units} {self._more(describing)}", "value": f"than:{b[0]}",
                                    "sure": round(min(a[2], b[2]) * 0.95, 2), "keep": False,
                                    "because": f"{a[0]} is {a[1]} {words_plural(unit)} {describing} and {b[0]} is {b[1]}"})
        return out

    # 7. time order -------------------------------------------------------------
    def _order(self, known: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """"I ate breakfast before work", "I went to work before the gym" ->
        breakfast came before the gym. ("after" is the same the other way.)"""
        edges = []  # (earlier words, earlier text, later words, later text, fact, fact_is_earlier, sure)
        for f in known:
            obj = str(f.get("object") or "")
            m = re.search(r"\s(before|after)\s", obj)
            if not m:
                continue
            mine, other = obj[: m.start()].strip(), obj[m.end():].strip()
            predicate = str(f.get("predicate") or "")
            verb = predicate.split("v:", 1)[1].split("@", 1)[0] if "v:" in predicate else predicate
            event_words = word_lemmas(f"{verb} {mine}")
            prep = predicate.split("@", 1)[1] if "@" in predicate else ""
            event_text = f"{self._said_verb(f, verb)} {prep} {mine}".replace("  ", " ").strip()
            other_words = word_lemmas(other)
            if m.group(1) == "before":
                edges.append((event_words, event_text, other_words, other, f, True, self._sure(f)))
            else:
                edges.append((other_words, other, event_words, event_text, f, False, self._sure(f)))
        out = []
        for e1 in edges:
            for e2 in edges:
                if e1 is e2 or not e1[2] or not e2[0]:
                    continue
                if e1[2] <= e2[0] or e2[0] <= e1[2]:  # the later one of e1 is the earlier one of e2
                    fact, earlier = (e1[4], True) if e1[5] else (e2[4], False) if not e2[5] else (None, None)
                    if fact is None:
                        continue
                    mine = str(fact.get("object") or "")
                    mine = mine[: re.search(r"\s(before|after)\s", mine).start()].strip()
                    out.append({"subject": fact.get("subject"), "predicate": fact.get("predicate"),
                                "object": f"{mine} before {e2[3]}" if earlier else f"{mine} after {e1[1]}",
                                "value": fact.get("value"), "sure": round(e1[6] * e2[6] * 0.9, 2), "keep": False,
                                "because": f"{e1[1]} before {e1[3]}, and {e2[1]} before {e2[3]}"})
        return out

    @staticmethod
    def _said_verb(f: Dict[str, Any], verb: str) -> str:
        value = str(f.get("value") or "")
        return value[5:] if value.startswith("said:") else verb

    # 8. why, more than one step --------------------------------------------------
    def _happening(self, f: Dict[str, Any]) -> Tuple[str, Set[str], bool]:
        """A fact as a happening: its words, and whether it's a "not"."""
        who = "he" if str(f.get("subject")) == "user" else str(f.get("subject") or "")
        predicate = str(f.get("predicate") or "")
        negative = predicate.startswith("not_")
        plain = predicate.replace("not_", "")
        verb = plain.split("v:", 1)[1].split("@", 1)[0] if "v:" in plain else plain.replace("is_a", "is")
        obj = str(f.get("object") or "").replace("(nothing)", "").replace("user's ", "his ")
        said = self._said_verb(f, verb)
        text = f"{who} {'didn' + chr(39) + 't ' + verb if negative else said} {obj}".strip()
        return text, word_lemmas(f"{verb} {obj}"), negative

    def _why(self, known: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """"I'm tired because I didn't sleep", "I didn't sleep because I drank
        coffee" -> the coffee may be part of why he's tired. "If it rains the
        grass gets wet", "if the grass gets wet the dog gets muddy" -> if it
        rains the dog may get muddy."""
        links = []  # (cause text, cause words, cause not, effect text, effect words, effect not, sure, is_rule)
        for f in known:
            # His own "because" (memory keeps it); a guess's "because" is only
            # her explanation of how she got there, not a cause.
            told = isinstance(f.get("id"), int) and not str(f.get("held_by") or "").startswith("concluded")
            because = str(f.get("because") or "").strip() if told else ""
            if because:
                text, words, negative = self._happening(f)
                links.append((because, word_lemmas(because), is_negative(because), text, words, negative,
                              self._sure(f), False, f))
            if str(f.get("predicate") or "") == "then":
                a, b = str(f.get("subject") or ""), str(f.get("object") or "")
                links.append((a, word_lemmas(a), is_negative(a), b, word_lemmas(b), is_negative(b),
                              self._sure(f), True, None))
        out = []
        for first in links:        # cause -> middle
            for second in links:   # middle -> effect
                if first is second or first[5] != second[2]:
                    continue
                if same_happening(first[4], second[1]) < 0.6:
                    continue
                if same_happening(first[1], second[4]) >= 0.6:
                    continue  # going round in a circle
                sure = round(first[6] * second[6] * same_happening(first[4], second[1]) * 0.85, 2)
                out.append({"subject": first[0], "predicate": "then", "object": second[3],
                            "value": f"via:{first[3]}", "sure": sure,
                            # What it explains (as he told it) and the first cause, in his words.
                            "explains": second[8], "first_cause": first[0],
                            "because": f"{first[0]} led to {first[3]}, and {second[0]} led to {second[3]}; "
                                       f"so maybe {first[0]} is part of why {second[3]}"
                            if not (first[7] and second[7]) else
                            f"if {first[0]} then {first[3]}, and if {second[0]} then {second[3]}"})
        best: Dict[Tuple[str, str], Dict[str, Any]] = {}
        for c in out:  # one way there is enough: the surest
            k = (str(c["subject"]).casefold(), str(c["object"]).casefold())
            if k not in best or c["sure"] > best[k]["sure"]:
                best[k] = c
        return list(best.values())


__all__ = ["Engine", "RelationBeliefs", "AmountBeliefs", "words_plural", "PLACEHOLDER_BELIEFS", "number_in", "word_lemmas", "dictionary_kinds", "opposites", "base_noun",
           "is_kind_word"]
