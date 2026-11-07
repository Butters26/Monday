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

from typing import Any, Callable, Dict, List, Optional, Set
import re

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


def _hypernym_ids(noun: str, depth: int = 6) -> set:
    try:
        from lexicon.oewn_offline import get_wordnet
        wn = get_wordnet()
        frontier = [x for x in wn.synsets(str(noun or "").casefold(), pos="n")
                    if any(str(l) == str(noun).casefold() for l in x.lemmas())][:2]
    except Exception:
        return set()
    seen = set()
    for _ in range(depth):
        seen |= {x.id for x in frontier}
        frontier = [h for x in frontier for h in x.hypernyms()]
    return seen


def _ids_of(word: str) -> set:
    try:
        from lexicon.oewn_offline import get_wordnet
        return {x.id for x in get_wordnet().synsets(word, pos="n")
                if any(str(l) == word for l in x.lemmas())}
    except Exception:
        return set()


def family_kind(noun: str) -> Optional[str]:
    """Whether the dictionary puts a word under sibling or parent ("sister",
    "brother" -> sibling, by way of "female sibling"; "mom", "father" ->
    parent)."""
    above = _hypernym_ids(noun)
    try:
        from lexicon.oewn_offline import get_wordnet
        wn = get_wordnet()
        words = {w for i in above for l in wn.synset(i).lemmas() for w in str(l).casefold().split()}
    except Exception:
        words = set()
    for kind in ("sibling", "parent"):
        if above & _ids_of(kind) or kind in words:
            return kind
    return None


def fact_sure(fact: Dict[str, Any]) -> float:
    """How sure she is of a fact: its own 'sure' if reasoning set one, else
    how confident memory is in it."""
    for key in ("sure", "confidence"):
        try:
            value = float(fact.get(key))
            if 0.0 < value <= 1.0:
                return value
        except (TypeError, ValueError):
            continue
    return 0.8


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
        conclusions: List[Dict[str, Any]] = []
        said_relation = self.relation_in(reading or {})
        if said_relation:
            conclusions.append(said_relation)
        # Everything she knows that bears on this, and what follows from it all
        # (reasoning_engine.py: kinds, comparisons, opposites, relations).
        known = self.recall_around(said, facts, user_id) + ([said_relation] if said_relation else [])
        conclusions += self.conclude(known, user_id)
        # Guesses she made before that he has now said are wrong.
        overruled = self.engine().overruled(known)
        rule = self.rule_in(reading or {})
        if rule:
            conclusions.append(rule)
        follows = self.what_rules_say(said, reading or {}, user_id)
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
        shown = self.what_patterns_show(patterns or {}, known)
        maybe_why = self.maybe_why(said, patterns or {}, facts)
        if maybe_why:
            unsure.append(maybe_why)
        problem = self.problem_in(reading or {}, facts)
        return {"said": said, "user_id": user_id, "happened": happened, "conclusions": conclusions,
                "explanations": explanations + changed + shown, "her_feeling": feeling,
                "unsure": unsure + follows,
                "her_guesses": [f for f in known if str(f.get("held_by") or "").startswith("concluded")],
                **({"overruled": overruled} if overruled else {}),
                **({"problem": problem} if problem else {})}

    _engine = None

    def engine(self):
        if Understanding._engine is None:
            from reasoning_engine import Engine, RelationBeliefs, AmountBeliefs
            try:
                from runtime_paths import runtime_file
                path, amounts = runtime_file("reasoning_beliefs.txt"), runtime_file("reasoning_amounts.txt")
            except Exception:
                path = amounts = None
            Understanding._engine = Engine(family_kind, RelationBeliefs(path), AmountBeliefs(amounts))
        return Understanding._engine

    # ---- does Language's reading make sense? -----------------------------------
    @staticmethod
    def reading_problems(said: str, reading: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Reasoning hears the same words Language does, and checks Language's
        reading of them against the words and the dictionary, the way a person
        notices they misheard. A reading doesn't make sense when:
        - an action ending in -s ("dogs", "barks") has nobody doing it: an -s
          action always needs a doer, so a word the dictionary also has as a
          thing is more likely the doer ("dogs bark": dogs are the ones barking);
        - "can", "will" and the like are followed by a thing the dictionary
          also has as an action ("birds can fly": fly is what they can do);
        - someone ("I", "he"...) is followed by a thing the dictionary also has
          as an action, with no action for them before the next part
          ("I go to bed": go is what I do).
        Each problem says which word, what it was read as, what fits better
        and why. It's a guess: Language does the reading again."""
        from reasoning_engine import _ordinary
        tokens = [t for t in reading.get("tokens") or [] if isinstance(t, dict)]
        clauses = reading.get("clauses") or [{}]
        roles = (clauses[0] or {}).get("roles") or {}
        out: List[Dict[str, Any]] = []
        doers = ("i", "you", "he", "she", "we", "they", "it")
        doing = ("verb", "auxiliary", "modal")
        for n, t in enumerate(tokens):
            surface = str(t.get("surface") or "").casefold()
            lemma = str(t.get("lemma") or surface).casefold()
            kind = t.get("kind")
            before = tokens[n - 1] if n else {}
            after = tokens[n + 1:]
            if kind == "verb" and surface != lemma and surface in (lemma + "s", lemma + "es") \
                    and not (roles.get("agent") or roles.get("theme")) \
                    and not any(x.get("kind") in ("pronoun", "noun", "proper_noun") for x in tokens[:n]) \
                    and _ordinary(lemma, "n"):
                out.append({"word": t.get("surface"), "read_as": "an action", "fits_better": "a thing (the doer)",
                            "why": f"'{t.get('surface')}' as an action would need someone doing it, and nobody "
                                   f"is; the dictionary also has '{lemma}' as a thing, so '{t.get('surface')}' are "
                                   f"probably the ones doing it"})
            elif kind == "noun" and before.get("kind") == "modal" and _ordinary(lemma, "v"):
                out.append({"word": t.get("surface"), "read_as": "a thing", "fits_better": "an action",
                            "why": f"after '{before.get('surface')}' comes what can be done, and the dictionary "
                                   f"has '{surface}' as an action"})
            elif kind == "noun" and str(before.get("surface") or "").casefold() in doers \
                    and before.get("kind") == "pronoun" and _ordinary(surface, "v"):
                rest = []
                for x in after:
                    if x.get("kind") in ("pronoun", "subordinator", "conjunction", "preposition"):
                        break
                    rest.append(x)
                if not any(x.get("kind") in doing for x in rest):
                    out.append({"word": t.get("surface"), "read_as": "a thing", "fits_better": "an action",
                                "why": f"'{before.get('surface')}' has nothing they do unless '{surface}' is it, "
                                       f"and the dictionary has '{surface}' as an action"})
        # Nothing is done at all: "cats like fish" read as three things. After
        # the first thing, a word the dictionary has as an action is probably
        # what that thing does. (Also after a word just said to be the doer.)
        doers_now = {str(p["word"]).casefold() for p in out if "doer" in str(p.get("fits_better"))}
        # ("do"/"can" only help an action: "do cats like fish?" still needs one.)
        has_action = any(t.get("kind") == "verb" or (t.get("kind") == "auxiliary" and str(t.get("lemma")) in ("be", "have"))
                         for t in tokens if str(t.get("surface") or "").casefold() not in doers_now)
        if not has_action and not any(p.get("fits_better") == "an action" for p in out):
            for n, t in enumerate(tokens[:-1]):
                first = str(t.get("surface") or "").casefold()
                if t.get("kind") in ("determiner", "possessive", "adjective", "number"):
                    break  # "the big red ball": just naming something, no doer
                if t.get("kind") in ("noun", "proper_noun") or first in doers_now:
                    nxt = tokens[n + 1]
                    word = str(nxt.get("surface") or "")
                    if nxt.get("kind") in ("noun", "adjective") and _ordinary(
                            str(nxt.get("lemma") or word).casefold(), "v") or (
                            nxt.get("kind") == "noun" and _ordinary(word.casefold(), "v")):
                        out.append({"word": word, "read_as": "a thing", "fits_better": "an action",
                                    "why": f"nothing in it is being done unless '{word}' is it, and the "
                                           f"dictionary has '{word}' as an action that '{t.get('surface')}' "
                                           f"can be doing"})
                    break
        return out

    # ---- which of her memories are her own guesses ------------------------------
    @staticmethod
    def _concluded_path() -> Optional[str]:
        try:
            from runtime_paths import runtime_file
            return runtime_file("reasoning_concluded.json")
        except Exception:
            return None

    @classmethod
    def concluded_ids(cls) -> Set[int]:
        """Ids of the facts in memory that she worked out herself (not told)."""
        import json, os
        path = cls._concluded_path()
        try:
            if path and os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    return {int(i) for i in json.load(fh)}
        except Exception:
            pass
        return set()

    @classmethod
    def remember_concluded(cls, fact_id: Any) -> None:
        import json
        path = cls._concluded_path()
        try:
            ids = cls.concluded_ids() | {int(fact_id)}
            if path:
                with open(path, "w", encoding="utf-8") as fh:
                    json.dump(sorted(ids), fh)
        except Exception:
            pass

    def recall_around(self, said: str, facts: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
        """What she knows around this: the facts about what he said, then the
        facts about what those mention (a name, its kind, that kind's kind),
        two steps out, the way one memory brings up the next."""
        from reasoning_engine import base_noun
        gathered: Dict[Any, Dict[str, Any]] = {}
        for f in facts:
            gathered[f.get("id") or id(f)] = f
        asked = {said.strip().casefold()}
        for _ in range(2):
            words = set()
            for f in list(gathered.values()):
                for part in (f.get("subject"), f.get("object")):
                    w = str(part or "").replace("user's ", "").strip()
                    if w and w.casefold() not in ("user", "monday", "(nothing)"):
                        words.add(base_noun(w) if not w[:1].isupper() else w)
            for w in words - asked:
                asked.add(w)
                body = self.ask("notus", "query_facts", {"query": w, "user_id": user_id, "limit": 15}) or {}
                for f in body.get("facts") or []:
                    if isinstance(f, dict):
                        gathered[f.get("id") or id(f)] = f
        if "user" in " ".join(str(f.get("subject")) for f in gathered.values()):
            body = self.ask("notus", "query_facts", {"query": "user", "user_id": user_id, "limit": 40}) or {}
            for f in body.get("facts") or []:
                if isinstance(f, dict):
                    gathered[f.get("id") or id(f)] = f
        return self._mark_mine(list(gathered.values()))

    def conclude(self, known: List[Dict[str, Any]], user_id: str) -> List[Dict[str, Any]]:
        """What follows from what she knows. Before trusting a guess about
        something, she looks at what she knows about that thing itself
        ("a penguin can't fly" beats "birds fly")."""
        found = self.engine().infer(known)
        looked = {str(f.get("subject") or "").casefold() for f in known}
        more: List[Dict[str, Any]] = []
        for c in found:
            who = str(c.get("subject") or "")
            if who.casefold() not in looked:
                looked.add(who.casefold())
                body = self.ask("notus", "query_facts", {"query": who, "user_id": user_id, "limit": 15}) or {}
                more += [f for f in body.get("facts") or [] if isinstance(f, dict)]
        if more:
            have = {f.get("id") for f in known}
            known = known + self._mark_mine([f for f in more if f.get("id") not in have])
            found = self.engine().infer(known)
        wrong = self.rejected()
        return [c for c in found if self._guess_key(c) not in wrong]

    def _mark_mine(self, facts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        mine = self.concluded_ids()
        wrong = self.rejected()
        marked = [{**f, "held_by": "concluded"} if f.get("id") in mine and not f.get("held_by") else f for f in facts]
        # A guess of hers he said was wrong isn't something she knows any more.
        return [f for f in marked if not (str(f.get("held_by") or "").startswith("concluded")
                                          and self._guess_key(f) in wrong)]

    # ---- when he says she's wrong -------------------------------------------------
    @staticmethod
    def _guess_key(f: Dict[str, Any]) -> str:
        from reasoning_engine import Engine
        return "|".join(Engine._key(f))

    @classmethod
    def _rejected_path(cls) -> Optional[str]:
        try:
            from runtime_paths import runtime_file
            return runtime_file("reasoning_rejected.json")
        except Exception:
            return None

    @classmethod
    def rejected(cls) -> Set[str]:
        """Guesses of hers he said were wrong; she doesn't make them again."""
        import json, os
        path = cls._rejected_path()
        try:
            if path and os.path.exists(path):
                with open(path, encoding="utf-8") as fh:
                    return {str(k) for k in json.load(fh)}
        except Exception:
            pass
        return set()

    @classmethod
    def reject(cls, guesses: List[Dict[str, Any]]) -> None:
        import json
        path = cls._rejected_path()
        if not path:
            return
        try:
            keys = cls.rejected() | {cls._guess_key(g) for g in guesses}
            with open(path, "w", encoding="utf-8") as fh:
                json.dump(sorted(keys), fh)
        except Exception as error:
            print(f"⚠️  Reasoning: couldn't keep what he said was wrong ({error})")

    @staticmethod
    def _true_words() -> List[str]:
        """Her words for "true" (editable: reasoning_true_words.txt). Their
        dictionary opposites are her words for "wrong"."""
        placeholder = "# Words that mean something is true. Their opposites (false, wrong) come from the dictionary.\ntrue\ncorrect\nright\n"
        text = placeholder
        try:
            from runtime_paths import runtime_file
            from pathlib import Path
            path = Path(runtime_file("reasoning_true_words.txt"))
            if not path.exists():
                path.write_text(placeholder, encoding="utf-8")
            text = path.read_text(encoding="utf-8")
        except Exception:
            pass
        return [w.strip().casefold() for w in text.splitlines() if w.strip() and not w.strip().startswith("#")]

    @classmethod
    def is_denial(cls, said: str, reading: Dict[str, Any]) -> bool:
        """He says what she said isn't so: "no", "that's wrong", "that isn't
        true", "you're wrong", "no, Tweety can fly"."""
        from reasoning_engine import opposites
        words = re.findall(r"[a-z']+", said.casefold())
        if not words:
            return False
        tokens = [t for t in reading.get("tokens") or [] if t.get("kind") != "punctuation"]
        negative = lambda w: w in ("no", "not", "nope", "never") or w.endswith("n't")
        if negative(words[0]) and (len(words) == 1 or "," in said.split()[0]):
            return True  # "no" / "nope" / "no, ..."
        true_words = cls._true_words()
        false_words = {o.casefold() for w in true_words for o in opposites(w)}
        if any(w in false_words for w in words) and len(words) <= 4:
            return True  # "that's wrong", "you're wrong"
        if any(w in true_words for w in words) and any(negative(w) for w in words) and len(words) <= 5:
            return True  # "that isn't true", "not right"
        return False

    @staticmethod
    def guesses_in(reply: str, guesses: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Which of her guesses her reply said: its who and its what are both in it."""
        said = set(re.findall(r"[a-z']+", str(reply or "").casefold()))
        out = []
        for g in guesses:
            who = set(str(g.get("subject") or "").casefold().replace("user", "you").split())
            predicate = str(g.get("predicate") or "").replace("not_", "")
            what = set((predicate.split("v:", 1)[1].split("@")[0] if "v:" in predicate else "").split()) | \
                set(str(g.get("object") or "").casefold().replace("(nothing)", "").split())
            what = {w for w in what if len(w) > 2}
            if who and who <= said and what and (what & said):
                out.append(g)
        return out

    # ---- who is whose ----------------------------------------------------------
    def relation_in(self, reading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """"Lily is my sister", "Tom is Lily's son": whose relative someone is,
        filed the way memory files his family ("user", "sister", "Lily")."""
        clause = (reading.get("clauses") or [{}])[0]
        if not clause.get("copular"):
            return None
        tokens = [t for t in reading.get("tokens") or [] if t.get("kind") != "punctuation"]
        names = [t for t in tokens if t.get("kind") == "proper_noun"]
        be = next((i for i, t in enumerate(tokens) if t.get("kind") == "auxiliary"), None)
        if be is None or not names or tokens[0].get("kind") != "proper_noun":
            return None
        who = str(tokens[0].get("surface") or "")
        after = tokens[be + 1:]
        if not after:
            return None
        relative = str(after[-1].get("lemma") or "").casefold()
        if after[-1].get("kind") != "noun" or kind_of(relative) != "person":
            return None
        owner_word = str(after[0].get("surface") or "").casefold()
        if owner_word in ("my", "our"):
            owner = "user"
        elif owner_word.endswith("'s") and owner_word[:-2]:
            owner = str(after[0].get("surface"))[:-2]
            owner = owner[:1].upper() + owner[1:]
        else:
            return None
        return {"subject": owner, "predicate": relative, "object": who[:1].upper() + who[1:], "sure": 0.95,
                "because": f"he said: {reading.get('raw_text')}"}

    # ---- if this, then that ----------------------------------------------------
    def rule_in(self, reading: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """"If it rains we will stay home": a rule he gave, kept (as concluded,
        not as anything having happened) to use when the first part comes true."""
        links = [l for l in reading.get("links") or [] if l.get("kind") == "on_condition"]
        parts = reading.get("parts") or []
        if not links or not parts:
            return None
        a, b = links[0].get("from"), links[0].get("to")
        if not (isinstance(a, int) and isinstance(b, int) and a < len(parts) and b < len(parts)):
            return None
        return {"subject": parts[b], "predicate": "then", "object": parts[a], "sure": 0.7,
                "because": f"he said: {reading.get('raw_text')}"}

    def what_rules_say(self, said: str, reading: Dict[str, Any], user_id: str) -> List[str]:
        """A rule he gave whose first part is what he's saying now: what it says
        follows, as a guess ("he said if it rains they stay home; it rains now,
        so they'll probably stay home")."""
        if reading.get("links") and any(l.get("kind") == "on_condition" for l in reading.get("links") or []):
            return []  # this is the rule itself
        words = {str(t.get("lemma") or "").casefold() for t in reading.get("tokens") or []
                 if t.get("kind") in ("noun", "verb", "adjective", "proper_noun")}
        if not words:
            return []
        body = self.ask("notus", "query_facts", {"query": said, "user_id": user_id, "limit": 30}) or {}
        out = []
        for f in body.get("facts") or []:
            if str(f.get("predicate")) != "then":
                continue
            needed = {w.strip(".,!?").casefold() for w in str(f.get("subject") or "").split()} - {
                "it", "i", "we", "you", "the", "a", "an", "is", "are", "will"}
            lemmas_needed = {w[:-1] if w.endswith("s") else w for w in needed}
            have = words | {w[:-1] if w.endswith("s") else w for w in words}
            if needed and (needed <= have or lemmas_needed <= have):
                out.append(f"he said if {f.get('subject')}, {f.get('object')}; that's happening now, so "
                           f"probably {f.get('object')} (a guess, sure {round(fact_sure(f) * 0.9, 2)})")
        return out

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
            if not kind or kind == "person":
                continue  # ("brother", "teacher": who someone is to him, not a new kind of thing)
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
    def what_patterns_show(patterns: Dict[str, Any], facts: Optional[List[Dict[str, Any]]] = None) -> List[str]:
        """What Pattern Recognition found, and what it does and doesn't show:
        things coming up together isn't one causing the other. A run of steps
        is only something happening when each step is a thing or doing she
        knows about; a run of bare words ("penguin then can't then fly") is
        just the order he said them in."""
        out: List[str] = []
        things: Set[str] = set()
        for f in facts or []:
            predicate = str(f.get("predicate") or "")
            for part in (f.get("subject"), f.get("object"), predicate.split("v:", 1)[1] if "v:" in predicate else ""):
                things.update(w for w in str(part or "").casefold().replace("_", " ").split() if w)
        if isinstance(patterns.get("significant_patterns"), dict):
            patterns = patterns["significant_patterns"]  # as Thalamus hands it over
        for p in (patterns.get("strong_co_occurrences") or [])[:3]:
            items = [str(i) for i in p.get("items") or []]
            if len(items) == 2:
                out.append(f"{items[0]} and {items[1]} keep coming up together ({p.get('count')} times); "
                           "that alone doesn't show one causes the other")
        for p in (patterns.get("reliable_sequences") or [])[:2]:
            steps = [str(x) for x in p.get("steps") or []]
            if facts is not None and not all(set(st.casefold().split()) & things for st in steps):
                continue
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
        # "A penguin can't fly", "fish can't walk": what a whole kind is like,
        # not something going wrong for him.
        from reasoning_engine import is_kind_word, base_noun
        first = who.split()[0].casefold() if who else ""
        if first in ("a", "an") or (who and who[:1].islower() and is_kind_word(who) and len(who.split()) == 1
                                    and who.casefold() != base_noun(who)):
            return None
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
        parts = self.parts_of(head)
        if parts:
            # Working it out: what the thing is made of, any of which might be the trouble.
            out.setdefault("maybe", []).append(
                f"a {head} has parts ({', '.join(parts[:5])}); one of them may not be working (a guess)")
        about = [f for f in facts if head and head in f"{f.get('subject')} {f.get('object')}".casefold()
                 and str(f.get("predicate") or "") not in ("solved_by",)]
        if about and verb in ("find", "locate"):
            out.setdefault("maybe", []).append(
                "what she knows about it: " + "; ".join(self._said(f) for f in about[:3]))
        if not out.get("maybe"):
            out["unsure"] = "she doesn't know a way to fix this yet; she'd need to know more or be told"
        return out

    @staticmethod
    def parts_of(noun: str) -> List[str]:
        """What the dictionary says a thing is made of (a car: engine, ...)."""
        try:
            from lexicon.oewn_offline import get_wordnet
            synsets = [x for x in get_wordnet().synsets(str(noun or "").casefold(), pos="n")
                       if any(str(l) == str(noun).casefold() for l in x.lemmas())][:1]
            out = []
            for x in synsets:
                for part in x.meronyms() if hasattr(x, "meronyms") else []:
                    out.append(str(part.lemmas()[0]))
            return out
        except Exception:
            return []

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
