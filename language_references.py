"""Who "he", "she", "it" and "they" mean (Language's job: its contract says it
"uses supplied context to resolve references and ambiguity. Unfamiliar or
unresolved language remains explicitly uncertain.").

The context is supplied by whoever asks Language to read (memory supplies the
recent conversation and what it knows about names). Nothing here is a list of
names or genders:
- Whether a word means a man or a woman comes from the dictionary (a sister is
  a "female person"; a husband a "male person").
- Whether something is a person, an animal or a thing comes from the
  dictionary's filing of the noun.
- What memory knows about a name ("Lily is_a sister") tells what Lily is.
- Once a pronoun is settled on someone, Language remembers that this person
  is a he/she/they (a belief, changed if later talk shows otherwise).

The pronoun goes to the most recent mention it fits. If two different people
fit equally well, it stays uncertain and both are listed.
"""

from __future__ import annotations

import json
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

_SUBJECTS = {"he": "he", "him": "he", "his": "he", "himself": "he",
             "she": "she", "her": "she", "hers": "she", "herself": "she",
             "it": "it", "its": "it", "itself": "it",
             "they": "they", "them": "they", "their": "they", "theirs": "they", "themselves": "they"}
_POSSESSIVE_FORMS = {"his", "her", "its", "their"}
_SPEAKERS = {"i", "me", "my", "mine", "you", "your", "yours", "we", "us", "our"}

# Dictionary senses for the two sexes (person and animal senses of each).
_FEMALE = {"oewn-09642198-n", "oewn-01323363-n"}
_MALE = {"oewn-09647338-n", "oewn-01323721-n"}


def _wordnet():
    from lexicon.oewn_offline import get_wordnet
    return get_wordnet()


_kind_cache: Dict[str, Tuple[str, Optional[str]]] = {}
_kind_lock = threading.Lock()


def noun_kind(noun: str) -> Tuple[str, Optional[str]]:
    """("person"|"animal"|"thing", "she"|"he"|None) for a noun, from the dictionary."""
    key = noun.casefold()
    with _kind_lock:
        if key in _kind_cache:
            return _kind_cache[key]
    kind, sex = "thing", None
    try:
        synsets = list(_wordnet().synsets(key, pos="n"))
    except Exception:
        synsets = []
    if synsets:
        first = str(synsets[0].lexfile())
        kind = {"noun.person": "person", "noun.animal": "animal"}.get(first, "thing")
        votes = {"she": 0, "he": 0}
        for synset in synsets[:4]:
            if str(synset.lexfile()) != first:
                continue
            seen, stack = set(), [synset]
            while stack:
                node = stack.pop()
                for up in node.hypernyms() + list(node.relations().get("instance_hypernym", [])):
                    if up.id not in seen:
                        seen.add(up.id)
                        stack.append(up)
            if seen & _FEMALE:
                votes["she"] += 1
            if seen & _MALE:
                votes["he"] += 1
        if votes["she"] != votes["he"]:
            sex = "she" if votes["she"] > votes["he"] else "he"
    with _kind_lock:
        _kind_cache[key] = (kind, sex)
    return kind, sex


def _only_a_place(name: str) -> bool:
    try:
        synsets = list(_wordnet().synsets(name, pos="n"))
    except Exception:
        return False
    return bool(synsets) and all(str(ss.lexfile()) == "noun.location" for ss in synsets)


class PeopleBeliefs:
    """What Language has come to believe about how people are referred to."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = Path(path) if path else None
        self.lock = threading.Lock()
        self.known: Dict[str, Dict[str, str]] = {}
        if self.path and self.path.is_file():
            try:
                self.known = json.loads(self.path.read_text(encoding="utf-8")).get("people", {})
            except Exception as exc:
                print(f"⚠️  Language: could not read {self.path}: {exc}")

    def pronoun_for(self, user_id: str, name: str) -> Optional[str]:
        with self.lock:
            return (self.known.get(user_id) or {}).get(name.casefold())

    def learn(self, user_id: str, name: str, pronoun: str) -> None:
        if pronoun not in ("he", "she", "they"):
            return
        with self.lock:
            people = self.known.setdefault(user_id, {})
            if people.get(name.casefold()) == pronoun:
                return
            people[name.casefold()] = pronoun
            if self.path:
                try:
                    self.path.parent.mkdir(parents=True, exist_ok=True)
                    self.path.write_text(json.dumps({"people": self.known}, indent=2), encoding="utf-8")
                except Exception as exc:
                    print(f"⚠️  Language: could not save {self.path}: {exc}")


def _raw_words(raw: str) -> List[str]:
    return re.findall(r"[A-Za-z][A-Za-z'-]*", raw or "")


def _candidates(reading: Dict[str, Any], people: Dict[str, List[str]], beliefs: PeopleBeliefs,
                user_id: str, stop_at: Optional[int] = None) -> List[Dict[str, Any]]:
    """Everyone and everything a sentence mentions, in order, with what they are."""
    tokens = [t for t in reading.get("tokens") or [] if t.get("kind") != "punctuation"]
    words = _raw_words(str(reading.get("raw_text") or ""))
    known_names = {n.casefold(): n for n in people}
    found: List[Dict[str, Any]] = []
    names_here: List[Dict[str, Any]] = []
    for pos, token in enumerate(tokens):
        if stop_at is not None and int(token.get("index", pos)) >= stop_at:
            break
        surface = str(token.get("surface") or "")
        low = surface.casefold()
        if low in _SPEAKERS or low in _SUBJECTS or low in ("monday", "mercy"):
            continue
        raw = words[pos] if pos < len(words) else surface
        raw = raw[:-2] if raw.endswith("'s") else raw
        is_name = token.get("kind") == "proper_noun" or low.rstrip("'s") in known_names or (
            raw[:1].isupper() and pos > 0)
        if is_name:
            name = known_names.get(low.rstrip("'s"), raw[:1].upper() + raw[1:])
            what = people.get(name) or []
            kind, sex = "person", None
            before_word = str((tokens[pos - 1] if pos > 0 else {}).get("kind") or "")
            if not what and (before_word == "preposition" or _only_a_place(name)):
                # "in Paris": a name the dictionary only knows as a place, or one
                # right after in/at/to/from, is a place unless memory knows a person.
                kind = "thing"
            for noun in what:
                k, s = noun_kind(noun)
                kind, sex = k, s or sex
                if s:
                    break
            sex = sex or beliefs.pronoun_for(user_id, name)
            entry = {"entity": {"name": name}, "kind": kind, "sex": sex, "plural": False, "label": name}
            found.append(entry)
            names_here.append(entry)
            continue
        if token.get("kind") in ("noun",) or (token.get("kind") == "possessive" and token.get("senses")):
            lemma = str(token.get("lemma") or "").casefold()
            if not lemma:
                continue
            kind, sex = noun_kind(lemma)
            before = tokens[pos - 1] if pos > 0 else {}
            owner_word = str(before.get("surface") or "").casefold()
            owner = {"my": "user", "our": "user", "your": "monday"}.get(owner_word)
            if not owner and before.get("kind") == "possessive":
                o = str(before.get("lemma") or "")
                owner = o[:1].upper() + o[1:]
            plural = surface.casefold() != lemma and surface.casefold().endswith("s") and token.get("kind") == "noun"
            entity = {"noun": lemma, "owner": owner} if owner else {"noun": lemma, "definite": True}
            label = (f"{'my' if owner == 'user' else 'your' if owner == 'monday' else (owner + chr(39) + 's') if owner else 'the'} {surface}")
            found.append({"entity": entity, "kind": kind, "sex": sex, "plural": plural, "label": label})
    found = _same_ones(reading, found)
    names_here = [c for c in found if "name" in c["entity"]]
    if len(names_here) >= 2:
        # "Ariana and Cleo": together they are a "they".
        found.append({"entity": {"names": [n["entity"]["name"] for n in names_here]}, "kind": "person",
                      "sex": None, "plural": True, "label": " and ".join(n["label"] for n in names_here)})
    return found


def _same_ones(reading: Dict[str, Any], found: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A name and a noun that are one person: "Lily is my sister" (the
    sentence says they're the same) and "my brother Tom" (side by side).
    The name stays; it takes what the noun says she or he is."""
    copular = bool((reading.get("assertion") or {}).get("copular"))
    merged: List[Dict[str, Any]] = []

    def merge(name: Dict[str, Any], noun: Dict[str, Any]) -> None:
        if noun["kind"] in ("person", "animal") or name["kind"] == "person":
            name.update({"kind": noun["kind"] if noun["kind"] != "thing" else name["kind"],
                         "sex": noun["sex"] or name["sex"]})
        merged.append(noun)

    # Side by side first ("my sister Cleo"), then what the sentence says she is
    # ("... is a painter").
    for i in range(len(found) - 1):
        if "noun" in found[i]["entity"] and "name" in found[i + 1]["entity"] \
                and found[i]["kind"] in ("person", "animal"):
            merge(found[i + 1], found[i])
    left = [c for c in found if not any(c is m for m in merged)]
    names = [c for c in left if "name" in c["entity"]]
    nouns = [c for c in left if "noun" in c["entity"]]
    if copular and len(names) == 1 and len(nouns) == 1:
        merge(names[0], nouns[0])
    return [c for c in found if not any(c is m for m in merged)]


def _fit(pronoun: str, cand: Dict[str, Any]) -> float:
    """How well a pronoun fits a mention (0 = it can't)."""
    kind, sex, plural = cand["kind"], cand["sex"], cand["plural"]
    if pronoun == "it":
        return 0.0 if plural or kind == "person" else (1.0 if kind == "thing" or sex is None else 0.5)
    if pronoun in ("he", "she"):
        if plural or kind == "thing":
            return 0.0
        if sex == pronoun:
            return 1.0
        if sex is None:
            # Someone whose sex she doesn't know might be a he or she; an
            # animal is usually an "it" unless the speaker knows it.
            return 0.6 if kind == "person" else 0.3
        return 0.0
    if pronoun == "they":
        if plural:
            return 1.0
        if kind == "person" and sex is None:
            return 0.5  # one person whose gender she doesn't know
        return 0.0
    return 0.0


def resolve(reading: Dict[str, Any], context: List[str], people: Dict[str, List[str]],
            analyze: Callable[[str], Dict[str, Any]], beliefs: PeopleBeliefs, user_id: str) -> Dict[str, Any]:
    """Add reading["references"]: what each he/she/it/they means, or that it's uncertain."""
    tokens = reading.get("tokens") or []
    pronouns = [t for t in tokens if str(t.get("surface") or "").casefold() in _SUBJECTS]
    if not pronouns:
        reading["references"] = []
        return reading
    # Mentions to look back on: this sentence first, then the last lines, newest first.
    earlier: List[Tuple[int, List[Dict[str, Any]]]] = []
    for age, line in enumerate(context or [], start=1):
        earlier.append((age, _candidates(analyze(line), people, beliefs, user_id)))
    references = []
    taken: Dict[str, str] = {}  # who each pronoun form already means in this sentence
    for token in pronouns:
        word = str(token.get("surface") or "").casefold()
        pronoun = _SUBJECTS[word]
        here = _candidates(reading, people, beliefs, user_id, stop_at=int(token.get("index", 0)))
        scored = []
        for age, cands in [(0, here)] + earlier:
            for order, cand in enumerate(cands):
                fit = _fit(pronoun, cand)
                # "He loves it": two different pronouns in one sentence are two different ones.
                if any(form != pronoun and label == cand["label"].casefold() for form, label in taken.items()):
                    fit = 0.0
                if fit > 0:
                    # Newer is more likely; later in the same line is more likely.
                    scored.append((fit / (1 + age) + order * 0.001, cand))
        scored.sort(key=lambda s: s[0], reverse=True)
        ref: Dict[str, Any] = {"index": token.get("index"), "pronoun": word, "refers_to": None,
                               "sure": False, "candidates": [c["label"] for _, c in scored[:3]]}
        if scored:
            best_score, best = scored[0]
            rival = next((c for s, c in scored[1:] if c["label"].casefold() != best["label"].casefold()), None)
            rival_score = next((s for s, c in scored[1:] if c["label"].casefold() != best["label"].casefold()), 0.0)
            if rival is None or best_score - rival_score > 0.05:
                ref.update({"refers_to": best["entity"], "label": best["label"], "sure": True})
                taken[pronoun] = best["label"].casefold()
                if "name" in best["entity"] and best["sex"] is None and pronoun in ("he", "she"):
                    beliefs.learn(user_id, best["entity"]["name"], pronoun)
            else:
                ref["why_uncertain"] = f"'{word}' could be {best['label']} or {rival['label']}"
        else:
            ref["why_uncertain"] = f"nothing said recently that '{word}' fits"
        references.append(ref)
    reading["references"] = references
    by_index = {r["index"]: r for r in references}
    for mention in reading.get("mentions") or []:
        if mention.get("pronoun") and mention.get("start") in by_index and by_index[mention["start"]]["sure"]:
            mention["refers_to"] = by_index[mention["start"]]["refers_to"]
    sure = {r["index"] for r in references if r["sure"]}
    reading["unresolved_references"] = [
        u for u in reading.get("unresolved_references") or []
        if not any(m.get("mention_id") == u.get("mention_id") and m.get("start") in sure
                   for m in reading.get("mentions") or [])]
    return reading


__all__ = ["resolve", "PeopleBeliefs", "noun_kind"]
