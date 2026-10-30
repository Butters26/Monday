"""Sentence builder for the Language lobe: meaning in, sentence out, learning always on.

Language's expression half. It takes a meaning (who, what, to whom, and whether
Monday is telling, asking, or greeting) and builds the sentence itself:

- words come from the meaning and the offline OEWN dictionary (synonyms, word
  types, irregular forms) -- never from canned replies or copied user sentences;
- grammar is general rules: word order, verb agreement and tense, modals,
  negation, questions, articles, plurals, pronouns, possessives, joining facts;
- every place where more than one correct option exists is a *choice*. No
  option is given a head start and there are no example lists: every option
  starts equal (0.5), and greeting words come from the dictionary sense for
  greeting. Each option keeps a success record in Language's own learning store
  (learning/lobe_learning_store.py, lobe "language"): how often it was used and
  how often its sentence was judged good. The builder prefers options with a
  better record and sometimes tries others. Records persist across restarts and
  are kept per learner, so game contestants learn apart.

Not wired into Monday's live replies yet; LanguageGenerator.express() and the
"express" / "express_feedback" messages expose it.

Meaning format (all keys optional except what the act needs):

    {
      "act": "state" | "ask" | "greet",
      "subject": <entity>,            # who/what the sentence is about
      "verb": "devour",               # lemma; "be" with "complement" for X is Y
      "object": <entity>,
      "recipient": <entity>,          # gave Jester *to Matthew*
      "complement": {"noun": "wife", "of": <entity>, "adjectives": [...]}
                  | {"adjectives": ["sweet", "loving"]}
                  | {"entity": <entity>}        # Your name is *Matthew*
                  | {"phrase": "almost dead"},  # stored wording, used as is
      "modifiers": [{"prep": "with", "object": <entity>}],
      "modal": "can" | "will" | "should" | ...,
      "negated": False,
      "tense": "present" | "past" | "future",
      "ask_about": None | "subject" | "object" | "reason",   # for act "ask"
      "addressee": <entity>,          # for act "greet"
    }

    entity = {"name": "Matthew"}                      # proper name
           | {"ref": "speaker"} | {"ref": "addressee"}  # I / you
           | {"noun": "fire", "count": "mass" | "one" | "many",
              "definite": True|False, "adjectives": [...],
              "owner": <entity>,                  # *your* name, *Matthew's* dog
              "modifiers": [{"prep": "with", "object": <entity>}]}
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Sequence, Tuple

LEARNING_LOBE = "language"
KEY_PREFIX = "speak:"
EXPLORE_RATE = 0.1
START_SCORE = 0.5   # every option starts equal; nothing is preferred until learned
# OEWN sense "an expression of greeting" (hello, hullo, hi, howdy, how-do-you-do).
GREETING_SENSE = "oewn-06645018-n"

_MODALS = {"can", "could", "will", "would", "shall", "should", "may", "might", "must"}
_BE_PRESENT = {("1", "sg"): "am", ("2", "sg"): "are", ("3", "sg"): "is",
               ("1", "pl"): "are", ("2", "pl"): "are", ("3", "pl"): "are"}
_BE_PAST = {("1", "sg"): "was", ("2", "sg"): "were", ("3", "sg"): "was",
            ("1", "pl"): "were", ("2", "pl"): "were", ("3", "pl"): "were"}
# Helper verbs whose forms are irregular in ways the dictionary lists unordered.
_IRREGULAR_HELPERS = {
    "have": {"third": "has", "past": "had", "participle": "had"},
    "do": {"third": "does", "past": "did", "participle": "done"},
}
_AN_EXCEPTIONS_AN = ("hour", "honest", "honor", "honour", "heir")
_AN_EXCEPTIONS_A = ("uni", "use", "usu", "uti", "one", "once", "eu", "ewe")
_PRONOUNS = {
    "speaker": {"subject": "I", "object": "me", "possessive": "my"},
    "addressee": {"subject": "you", "object": "you", "possessive": "your"},
}


# --------------------------------------------------------------------------
# Dictionary access (offline OEWN). Degrades to rules when unavailable.
# --------------------------------------------------------------------------

class Lexicon:
    def __init__(self) -> None:
        self._wn = None
        self._error: Optional[str] = None
        try:
            from lexicon.oewn_offline import get_wordnet
            self._wn = get_wordnet()
        except Exception as exc:  # report honestly; rules still work
            self._error = str(exc)

    @property
    def available(self) -> bool:
        return self._wn is not None

    def irregular_forms(self, lemma: str, pos: str) -> List[str]:
        if not self._wn:
            return []
        try:
            words = self._wn.words(lemma, pos=pos)
        except Exception:
            return []
        for word in words:
            if str(word.lemma()).casefold() == lemma.casefold():
                return [f for f in word.forms() if f.casefold() != lemma.casefold()]
        return []

    def sense_words(self, synset_id: str) -> List[str]:
        """All single-token words the dictionary lists for one sense."""
        if not self._wn:
            return []
        try:
            synset = self._wn.synset(synset_id)
        except Exception:
            return []
        return [str(x) for x in synset.lemmas() if re.fullmatch(r"[a-z]+(?:-[a-z]+)*", str(x))]

    def synonyms(self, lemma: str, pos: str) -> List[str]:
        """Single-word synonyms from the word's most common sense."""
        if not self._wn:
            return []
        try:
            synsets = self._wn.synsets(lemma, pos=pos)
        except Exception:
            return []
        for synset in synsets:
            lemmas = [str(x) for x in synset.lemmas()]
            if lemma.casefold() not in (x.casefold() for x in lemmas):
                continue
            return [x for x in lemmas
                    if x.casefold() != lemma.casefold() and re.fullmatch(r"[a-z]+", x)]
        return []


# --------------------------------------------------------------------------
# Morphology rules
# --------------------------------------------------------------------------

def _is_vowel(ch: str) -> bool:
    return ch.lower() in "aeiou"


def _double_final(word: str) -> bool:
    """stop -> stopped: one-syllable consonant-vowel-consonant endings."""
    if len(word) < 3 or word[-1] in "wxy":
        return False
    vowels = sum(1 for c in word if _is_vowel(c))
    return (vowels == 1 and not _is_vowel(word[-1]) and _is_vowel(word[-2])
            and not _is_vowel(word[-3]))


def third_person_s(verb: str) -> str:
    if verb.endswith(("s", "sh", "ch", "x", "z", "o")):
        return verb + "es"
    if verb.endswith("y") and len(verb) > 1 and not _is_vowel(verb[-2]):
        return verb[:-1] + "ies"
    return verb + "s"


def regular_past(verb: str) -> str:
    if verb.endswith("e"):
        return verb + "d"
    if verb.endswith("y") and len(verb) > 1 and not _is_vowel(verb[-2]):
        return verb[:-1] + "ied"
    if _double_final(verb):
        return verb + verb[-1] + "ed"
    return verb + "ed"


def regular_plural(noun: str) -> str:
    if noun.endswith(("s", "sh", "ch", "x", "z")):
        return noun + "es"
    if noun.endswith("y") and len(noun) > 1 and not _is_vowel(noun[-2]):
        return noun[:-1] + "ies"
    return noun + "s"


def indefinite_article(word: str) -> str:
    w = word.lower()
    if w.startswith(_AN_EXCEPTIONS_AN):
        return "an"
    if w.startswith(_AN_EXCEPTIONS_A):
        return "a"
    return "an" if w[:1] and _is_vowel(w[0]) else "a"


# --------------------------------------------------------------------------
# Learned choices
# --------------------------------------------------------------------------

@dataclass
class Built:
    """A sentence plus every choice that went into it (for feedback)."""
    sentence: str
    choices: List[Tuple[str, str, float]] = field(default_factory=list)  # (point, option, starting score)
    meaning: Any = None
    learner: str = "monday"
    problems: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return {"sentence": self.sentence, "choices": [list(c) for c in self.choices],
                "learner": self.learner, "problems": list(self.problems)}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Built":
        choices = [(str(c[0]), str(c[1]), float(c[2])) for c in data.get("choices", [])
                   if isinstance(c, (list, tuple)) and len(c) == 3]
        return cls(sentence=str(data.get("sentence", "")), choices=choices,
                   learner=str(data.get("learner") or "monday"),
                   problems=list(data.get("problems") or []))


class ChoiceMemory:
    """Success record for every choice option, kept in Language's learning store.

    Each option counts how often it was used and how often the sentence it was
    in was judged good. Its score is that success rate, smoothed so an untried
    option starts at 0.5 (equal to everything else). A good choice that shares
    a sentence with a bad one still rises over many sentences, because it shows
    up in the good ones too.
    """

    def __init__(self, learner: str, store: Any = None) -> None:
        self.learner = learner
        if store is None:
            from learning.lobe_learning_store import LobeLearningStore
            store = LobeLearningStore(LEARNING_LOBE)
        self.store = store
        self._cache: Optional[Dict[str, float]] = None

    @staticmethod
    def key(point: str, option: str) -> str:
        safe = re.sub(r"[^a-z0-9_-]+", "_", option.lower()).strip("_") or "x"
        return f"{KEY_PREFIX}{point}:{safe}"

    @staticmethod
    def rate(wins: int, tries: int) -> float:
        return (wins + 1.0) / (tries + 2.0)

    def _scores(self) -> Dict[str, float]:
        if self._cache is None:
            data = self.store._load()  # noqa: SLF001 - Language's own store
            facts = data.get("users", {}).get(self.learner, {}).get("facts", {})
            self._cache = {
                key: float(record.get("confidence", START_SCORE))
                for key, record in facts.items()
                if key.startswith(KEY_PREFIX) and isinstance(record, dict)
            }
        return self._cache

    def score(self, point: str, option: str, default: float) -> float:
        return self._scores().get(self.key(point, option), default)

    def record(self, choices: Sequence[Tuple[str, str, float]], good: bool, reason: str) -> List[Dict[str, Any]]:
        """Count one judged sentence against every choice that went into it."""
        scores = self._scores()
        changes: List[Dict[str, Any]] = []
        store = self.store
        with store._lock:  # noqa: SLF001
            data = store._load()  # noqa: SLF001
            facts = store._user_facts(data, self.learner)  # noqa: SLF001
            now = store._now()  # noqa: SLF001
            for point, option, _start in choices:
                key = self.key(point, option)
                rec = facts.get(key)
                if not isinstance(rec, dict):
                    rec = {"key": key, "fact": f"speaking choice {point} = {option}",
                           "status": "active", "source": "language_builder",
                           "wins": 0, "tries": 0, "evidence_count": 0, "contradiction_count": 0,
                           "use_count": 0, "last_applied_at": None, "created_at": now}
                rec["tries"] = int(rec.get("tries", 0)) + 1
                rec["wins"] = int(rec.get("wins", 0)) + (1 if good else 0)
                rec["evidence_count"] = rec["wins"]
                rec["contradiction_count"] = rec["tries"] - rec["wins"]
                rec["confidence"] = self.rate(rec["wins"], rec["tries"])
                if reason:
                    rec["last_reason"] = reason[:200]
                rec["updated_at"] = now
                facts[key] = rec
                scores[key] = rec["confidence"]
                changes.append({"choice": point, "option": option, "score": round(rec["confidence"], 3),
                                "wins": rec["wins"], "tries": rec["tries"]})
            store._save(data)  # noqa: SLF001
        return changes


# --------------------------------------------------------------------------
# The builder
# --------------------------------------------------------------------------

class SentenceBuilder:
    def __init__(self, learner: str = "monday", store: Any = None,
                 rng: Optional[random.Random] = None, explore_rate: float = EXPLORE_RATE,
                 lexicon: Optional[Lexicon] = None) -> None:
        self.learner = learner
        self.memory = ChoiceMemory(learner, store)
        self.rng = rng or random.Random()
        self.explore_rate = explore_rate
        self.lexicon = lexicon or Lexicon()

    # ---- choosing ---------------------------------------------------------

    def _choose(self, built: Built, point: str, options: Sequence[str]) -> str:
        """Pick among valid options by learned score. No option is favored up front."""
        options = list(dict.fromkeys(o for o in options if o))
        if not options:
            return ""
        if len(options) == 1:
            return options[0]
        scored = [(self.memory.score(point, o, START_SCORE), o) for o in options]
        if self.rng.random() < self.explore_rate:
            pick = self.rng.choice(options)
        else:
            best = max(s for s, _ in scored)
            pick = self.rng.choice([o for s, o in scored if s == best])
        built.choices.append((point, pick, START_SCORE))
        return pick

    def _word(self, built: Built, lemma: str, pos: str) -> str:
        """Pick a word for a meaning: the given word or a dictionary synonym."""
        options = [lemma] + self.lexicon.synonyms(lemma, pos)
        return self._choose(built, f"word_{pos}_{lemma.lower()}", options)

    # ---- noun phrases ------------------------------------------------------

    @staticmethod
    def _person_number(entity: Dict[str, Any]) -> Tuple[str, str]:
        ref = entity.get("ref")
        if ref == "speaker":
            return "1", "sg"
        if ref == "addressee":
            return "2", "sg"
        return "3", "pl" if entity.get("count") == "many" else "sg"

    def _plural(self, noun: str) -> str:
        for form in self.lexicon.irregular_forms(noun, "n"):
            return form
        return regular_plural(noun)

    def noun_phrase(self, built: Built, entity: Optional[Dict[str, Any]], case: str = "subject") -> str:
        if not entity:
            built.problems.append(f"missing {case}")
            return ""
        ref = entity.get("ref")
        if ref in _PRONOUNS:
            return _PRONOUNS[ref][case if case in ("subject", "object") else "object"]
        if entity.get("name"):
            phrase = str(entity["name"])
        elif entity.get("noun"):
            head = self._word(built, str(entity["noun"]), "n")
            count = entity.get("count", "one")
            if count == "many":
                head = self._plural(head)
            adjectives = [self._word(built, a, "a") for a in entity.get("adjectives", [])]
            body = " ".join(adjectives + [head])
            if entity.get("owner"):
                phrase = self.possessive(built, entity["owner"]) + " " + body
            elif entity.get("definite"):
                phrase = "the " + body
            elif count == "one":
                phrase = indefinite_article(body) + " " + body
            else:
                phrase = body
        else:
            built.problems.append(f"empty {case}")
            return ""
        for mod in entity.get("modifiers", []):
            inner = self.noun_phrase(built, mod.get("object"), "object")
            if inner and mod.get("prep"):
                phrase += f" {mod['prep']} {inner}"
        return phrase

    def possessive(self, built: Built, entity: Dict[str, Any]) -> str:
        ref = entity.get("ref")
        if ref in _PRONOUNS:
            return _PRONOUNS[ref]["possessive"]
        phrase = self.noun_phrase(built, entity, "object")
        return phrase + ("'" if phrase.endswith("s") and entity.get("count") == "many" else "'s")

    # ---- verbs -------------------------------------------------------------

    def _past(self, verb: str) -> Tuple[str, str]:
        """(simple past, past participle) from dictionary forms, else rules."""
        if verb in _IRREGULAR_HELPERS:
            helper = _IRREGULAR_HELPERS[verb]
            return helper["past"], helper["participle"]
        forms = [f for f in self.lexicon.irregular_forms(verb, "v") if not f.endswith("ing")
                 and f not in (third_person_s(verb),)]
        if not forms:
            regular = regular_past(verb)
            return regular, regular
        if len(forms) == 1:
            return forms[0], forms[0]
        participle = next((f for f in forms if f.endswith(("en", "ne", "wn"))), forms[-1])
        past = next((f for f in forms if f != participle), participle)
        return past, participle

    def _negate(self, built: Built, aux: str) -> str:
        style = self._choose(built, "negation_style", ["full", "contracted"])
        if style == "full":
            return "cannot" if aux == "can" else f"{aux} not"
        special = {"can": "can't", "will": "won't", "shall": "shan't", "am": "am not"}
        return special.get(aux, aux + "n't")

    def verb_group(self, built: Built, meaning: Dict[str, Any], subject: Dict[str, Any],
                   invert: bool = False) -> Tuple[str, str]:
        """Return (auxiliary-or-finite, rest). For questions the first part moves."""
        verb = str(meaning.get("verb") or "be").lower()
        tense = meaning.get("tense", "present")
        modal = (meaning.get("modal") or "").lower() or None
        negated = bool(meaning.get("negated"))
        pn = self._person_number(subject)
        if verb != "be":
            verb = self._word(built, verb, "v")

        if tense == "future" and not modal:
            modal = "will"
        if modal:
            aux = modal if modal in _MODALS else "can"
            if negated:
                aux = self._negate(built, aux)
            return aux, verb  # bare form after a modal; "be" stays "be"

        if verb == "be":
            form = (_BE_PAST if tense == "past" else _BE_PRESENT)[pn]
            if negated:
                form = self._negate(built, form)
            return form, ""

        if negated or invert:
            do = "did" if tense == "past" else ("does" if pn == ("3", "sg") else "do")
            if negated:
                do = self._negate(built, do)
            return do, verb
        if tense == "past":
            return self._past(verb)[0], ""
        if pn == ("3", "sg"):
            irregular = _IRREGULAR_HELPERS.get(verb, {}).get("third")
            return (irregular or third_person_s(verb)), ""
        return verb, ""

    # ---- clauses ------------------------------------------------------------

    def _complement(self, built: Built, comp: Dict[str, Any]) -> str:
        if comp.get("entity"):
            return self.noun_phrase(built, comp["entity"], "object")
        if comp.get("phrase"):
            return str(comp["phrase"]).strip()
        adjectives = [self._word(built, a, "a") for a in comp.get("adjectives", [])]
        if comp.get("noun"):
            noun = self._word(built, str(comp["noun"]), "n")
            owner = comp.get("of")
            pre = " ".join(adjectives)
            if owner:
                style = self._choose(built, "relation_style", ["possessive", "of"])
                if style == "possessive" and comp.get("definite", True):
                    return f"{self.possessive(built, owner)} {pre + ' ' if pre else ''}{noun}"
                owner_np = self.noun_phrase(built, owner, "object")
                article = "the" if comp.get("definite", True) else indefinite_article(pre or noun)
                return f"{article} {pre + ' ' if pre else ''}{noun} of {owner_np}"
            body = f"{pre} {noun}".strip()
            return f"{indefinite_article(body)} {body}" if not comp.get("definite") else f"the {body}"
        if adjectives:
            if len(adjectives) == 1:
                return adjectives[0]
            return ", ".join(adjectives[:-1]) + " and " + adjectives[-1]
        built.problems.append("empty complement")
        return ""

    def _predicate_tail(self, built: Built, meaning: Dict[str, Any]) -> str:
        parts: List[str] = []
        if meaning.get("complement"):
            parts.append(self._complement(built, meaning["complement"]))
        obj = meaning.get("object")
        recipient = meaning.get("recipient")
        if recipient and obj:
            order = self._choose(built, "recipient_order", ["to_phrase", "double_object"])
            o = self.noun_phrase(built, obj, "object")
            r = self.noun_phrase(built, recipient, "object")
            parts.append(f"{o} to {r}" if order == "to_phrase" else f"{r} {o}")
        elif obj:
            parts.append(self.noun_phrase(built, obj, "object"))
        for mod in meaning.get("modifiers", []):
            inner = self.noun_phrase(built, mod.get("object"), "object")
            if inner and mod.get("prep"):
                parts.append(f"{mod['prep']} {inner}")
        return " ".join(p for p in parts if p)

    def _statement(self, built: Built, meaning: Dict[str, Any]) -> str:
        subject = meaning.get("subject") or {}
        subj = self.noun_phrase(built, subject, "subject")
        finite, rest = self.verb_group(built, meaning, subject)
        tail = self._predicate_tail(built, meaning)
        return " ".join(p for p in (subj, finite, rest, tail) if p)

    def _question(self, built: Built, meaning: Dict[str, Any]) -> str:
        subject = meaning.get("subject") or {}
        about = meaning.get("ask_about")
        if about == "reason":
            finite, rest = self.verb_group(built, meaning, subject, invert=True)
            subj = self.noun_phrase(built, subject, "subject")
            tail = self._predicate_tail(built, meaning)
            return " ".join(p for p in ("why", finite, subj, rest, tail) if p)
        if about == "subject":
            wh = "who" if (meaning.get("subject") or {}).get("name") or not meaning.get("subject") else "what"
            wh_subject = {"count": "one"}
            finite, rest = self.verb_group(built, meaning, wh_subject)
            tail = self._predicate_tail(built, meaning)
            return " ".join(p for p in (wh, finite, rest, tail) if p)
        if about == "object":
            obj = meaning.get("object") or {}
            wh = "who" if obj.get("name") or obj.get("ref") else "what"
            reduced = dict(meaning)
            reduced.pop("object", None)
            finite, rest = self.verb_group(built, reduced, subject, invert=True)
            subj = self.noun_phrase(built, subject, "subject")
            tail = self._predicate_tail(built, reduced)
            return " ".join(p for p in (wh, finite, subj, rest, tail) if p)
        finite, rest = self.verb_group(built, meaning, subject, invert=True)
        subj = self.noun_phrase(built, subject, "subject")
        tail = self._predicate_tail(built, meaning)
        return " ".join(p for p in (finite, subj, rest, tail) if p)

    def _greeting(self, built: Built, meaning: Dict[str, Any]) -> str:
        words = self.lexicon.sense_words(GREETING_SENSE)
        if not words:
            built.problems.append("no greeting words: dictionary unavailable")
            return ""
        word = self._choose(built, "greeting_word", words)
        addressee = meaning.get("addressee")
        if addressee and addressee.get("name"):
            use_name = self._choose(built, "greeting_use_name", ["yes", "no"])
            if use_name == "yes":
                return f"{word}, {addressee['name']}"
        return word

    # ---- public --------------------------------------------------------------

    def build(self, meaning: Dict[str, Any]) -> Built:
        built = Built("", meaning=meaning, learner=self.learner)
        act = (meaning or {}).get("act", "state")
        if act == "greet":
            text, end = self._greeting(built, meaning), "!"
        elif act == "ask":
            text, end = self._question(built, meaning), "?"
        else:
            text, end = self._statement(built, meaning), "."
        text = re.sub(r"\s+", " ", text).strip()
        built.sentence = (text[:1].upper() + text[1:] + end) if text else ""
        if not text:
            built.problems.append("nothing built")
        return built

    def build_many(self, meanings: Sequence[Dict[str, Any]]) -> Built:
        """Several facts; same-subject statements may be joined with 'and'."""
        combined = Built("", meaning=list(meanings), learner=self.learner)
        sentences: List[str] = []
        i = 0
        meanings = list(meanings)
        while i < len(meanings):
            first = meanings[i]
            j = i + 1
            while (j < len(meanings) and first.get("act", "state") == "state"
                   and meanings[j].get("act", "state") == "state"
                   and meanings[j].get("subject") == first.get("subject")):
                j += 1
            group = meanings[i:j]
            if len(group) > 1 and self._choose(combined, "join_same_subject", ["join", "separate"]) == "join":
                head = self.build(group[0])
                tails = []
                for m in group[1:]:
                    b = Built("", learner=self.learner)
                    finite, rest = self.verb_group(b, m, m.get("subject") or {})
                    tail = self._predicate_tail(b, m)
                    tails.append(" ".join(p for p in (finite, rest, tail) if p))
                    combined.choices.extend(b.choices)
                    combined.problems.extend(b.problems)
                combined.choices.extend(head.choices)
                combined.problems.extend(head.problems)
                body = head.sentence.rstrip(".")
                if len(tails) == 1:
                    sentences.append(f"{body} and {tails[0]}.")
                else:
                    sentences.append(f"{body}, {', '.join(tails[:-1])}, and {tails[-1]}.")
            else:
                for m in group:
                    b = self.build(m)
                    combined.choices.extend(b.choices)
                    combined.problems.extend(b.problems)
                    sentences.append(b.sentence)
            i = j
        combined.sentence = " ".join(s for s in sentences if s)
        return combined

    def feedback(self, built: Built, good: bool, reason: str = "") -> Dict[str, Any]:
        """Learn from a judgment of a built sentence: adjust every choice it used."""
        changes = self.memory.record(built.choices, bool(good), reason)
        return {"good": good, "reason": reason, "learner": self.learner, "changes": changes}
