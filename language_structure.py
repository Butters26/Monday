"""How a long sentence is put together: Language's own small pattern reader.

Matthew (Nov 3): Language needs to recognize sentence patterns itself (a
small one inside Language), so long sentences don't confuse her. Pattern
Recognition will learn shapes across everything later; this is the part
Language uses while reading.

A long sentence is several simple statements put together. This finds them
and how they're joined, the way a reader does:

- an opener before a comma that isn't a statement ("no wait, ...", "well, ...")
- statements joined by and / but / or / so ("I got a job and I am happy"),
  including a second one that shares the first one's subject ("my sister and
  I went to the store and bought apples" -> "... bought apples")
- a statement inside another that says when / why / on what condition
  ("when I was a kid, I lived in Ohio", "she was tired because she worked")
- a statement about a thing, inside the sentence about it ("the dog that my
  sister owns is loud" -> "the dog is loud" + "my sister owns the dog")
- what someone thinks or says ("I think that you are getting better")

Each simple statement comes back as its own words, so every lobe can read it
on its own, plus how the statements are linked.

The small pattern part: the shape of every simple statement she reads (which
kinds of words in which order, "N V P N" for "I lived in Ohio") is counted
and kept. Where a sentence could be cut in more than one place, she cuts it
where the pieces have shapes she has seen most. She starts with no shapes and
learns them from what she reads. The grammar words used (and, because, that,
who...) are English's joining words, like the other word classes Language
already knows.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

# English's joining words (grammar, like Language's other word classes).
COORDINATORS = {"and", "but", "or", "so", "nor"}
SUBORDINATORS = {"because", "if", "although", "though", "while", "since", "until", "unless",
                 "after", "before", "once", "whereas", "when"}
RELATIVES = {"that", "who", "which", "whom"}

_VERBISH = ("verb", "auxiliary", "modal")
_NOMINAL = ("pronoun", "noun", "proper_noun", "determiner", "possessive", "number", "demonstrative")
_OBJECT_PRONOUNS = {"me", "him", "her", "us", "them"}
_SHAPE_LETTER = {
    "pronoun": "N", "noun": "N", "proper_noun": "N", "number": "N", "demonstrative": "N",
    "determiner": "D", "possessive": "D", "verb": "V", "auxiliary": "V", "modal": "V",
    "adjective": "A", "adverb": "R", "temporal": "R", "negation": "X", "preposition": "P",
    "conjunction": "C", "wh": "W", "subordinator": "C",
}


def _word(entry: Dict[str, Any]) -> str:
    return str(entry.get("surface") or "").casefold()


def _is_verbish(entry: Dict[str, Any]) -> bool:
    return entry.get("kind") in _VERBISH


class ShapeMemory:
    """The shapes of simple statements she has read, and how often."""

    def __init__(self, path: Optional[str] = None) -> None:
        self.path = path
        self.lock = threading.Lock()
        self.counts: Dict[str, int] = {}
        self._unsaved = 0
        if path:
            try:
                self.counts = {str(k): int(v) for k, v in json.loads(Path(path).read_text()).items()}
            except FileNotFoundError:
                pass
            except Exception as error:
                print(f"⚠️  Language: couldn't read the sentence shapes she has learned ({error}); starting with none")

    @staticmethod
    def shape(entries: Sequence[Dict[str, Any]]) -> str:
        letters: List[str] = []
        for entry in entries:
            letter = _SHAPE_LETTER.get(str(entry.get("kind") or ""), "?")
            if entry.get("kind") == "punctuation":
                continue
            if letters and letters[-1] == letter and letter in ("N", "V", "A", "R"):
                continue  # "my old dog" is one thing, "has been" one action
            if letter == "D":
                continue  # "the dog" and "dog" are the same shape
            letters.append(letter)
        return " ".join(letters)

    def seen(self, entries: Sequence[Dict[str, Any]]) -> int:
        return self.counts.get(self.shape(entries), 0)

    def learn(self, entries: Sequence[Dict[str, Any]]) -> None:
        key = self.shape(entries)
        if not key:
            return
        with self.lock:
            self.counts[key] = self.counts.get(key, 0) + 1
            self._unsaved += 1
            if self._unsaved >= 5:
                self.save()

    def save(self) -> None:
        if not self.path:
            return
        try:
            Path(self.path).write_text(json.dumps(self.counts, indent=0, sort_keys=True))
            self._unsaved = 0
        except Exception as error:
            print(f"⚠️  Language: couldn't save the sentence shapes she has learned ({error})")


class SentenceStructure:
    """Finds the simple statements in a sentence and how they're joined."""

    MAX_DEPTH = 4

    def __init__(self, shapes: ShapeMemory) -> None:
        self.shapes = shapes

    # ---- what a stretch of words is ----------------------------------------
    @staticmethod
    def _subject_end(seq: Sequence[Dict[str, Any]]) -> Optional[int]:
        """Where the subject at the start of a stretch ends (index of the first
        verb), if it opens with a subject followed by its verb."""
        i = 0
        while i < len(seq) and seq[i].get("kind") in ("adverb", "temporal", "negation"):
            i += 1  # "now I live", "maybe she"
        if i >= len(seq) or seq[i].get("kind") not in _NOMINAL:
            return None
        if seq[i].get("kind") == "pronoun" and _word(seq[i]) in _OBJECT_PRONOUNS \
                and not (i + 1 < len(seq) and _word(seq[i + 1]) == "and"):
            return None  # "him", "them": not a subject ("me and you" is)
        has_head = seq[i].get("kind") in ("pronoun", "noun", "proper_noun", "number", "demonstrative")
        for j in range(i + 1, len(seq)):
            if _is_verbish(seq[j]):
                return j
            if seq[j].get("kind") in ("preposition", "punctuation") or _word(seq[j]) in SUBORDINATORS | RELATIVES:
                return None
            if has_head and seq[j].get("kind") in ("pronoun", "determiner", "possessive") \
                    and _word(seq[j - 1]) != "and":
                return None  # "a kid I ...": a second thing starts; not one subject
            if seq[j].get("kind") in ("pronoun", "noun", "proper_noun", "number"):
                has_head = True
        return None

    def _starts_statement(self, seq: Sequence[Dict[str, Any]]) -> bool:
        return self._subject_end(seq) is not None

    @staticmethod
    def _has_verb(seq: Sequence[Dict[str, Any]]) -> bool:
        return any(_is_verbish(e) for e in seq)

    def _subject_of(self, seq: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        end = self._subject_end(seq)
        if end is None:
            return []
        start = 0
        while seq[start].get("kind") in ("adverb", "temporal", "negation"):
            start += 1
        return list(seq[start:end])

    # ---- cutting ----------------------------------------------------------
    def read(self, entries: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        """The simple statements in a sentence and how they're linked."""
        seq = [e for e in entries]
        result: Dict[str, Any] = {"opener": None, "pieces": [], "links": [], "frames": []}
        # An opener before a comma that isn't a statement: "no wait, ...".
        commas = [i for i, e in enumerate(seq) if e.get("kind") == "punctuation" and _word(e) == ","]
        if commas and commas[0] > 0:
            head = seq[:commas[0]]
            if not self._has_verb(head) and _word(head[0]) not in SUBORDINATORS \
                    and head[0].get("kind") != "wh" and self._has_verb(seq[commas[0] + 1:]):
                result["opener"] = {
                    "words": [str(e.get("surface")) for e in head],
                    "denies": any(e.get("kind") == "negation" for e in head),
                }
                seq = seq[commas[0] + 1:]
        pieces = self._split(seq, 0, result)
        index = {id(p): n for n, p in enumerate(pieces)}
        for link in result["links"]:
            link["from"], link["to"] = index.get(link["from"]), index.get(link["to"])
        for frame in result["frames"]:
            frame["piece"] = index.get(frame["piece"])
        result["pieces"] = pieces
        for piece in pieces:
            if self._starts_statement(piece["words"]):
                self.shapes.learn(piece["words"])
        return result

    def _split(self, seq: List[Dict[str, Any]], depth: int, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        if depth >= self.MAX_DEPTH or len(seq) < 3:
            return [{"words": self._clean(seq)}]
        for finder in (self._leading_condition, self._joined, self._relative, self._what_someone_thinks):
            found = finder(seq)
            if found is None:
                continue
            first, second, link = found
            right = self._split(second, depth + 1, result)
            if link.get("kind") == "held_by":
                # "I think ...": what's thought is the statement; who thinks it
                # is how it's held, not a statement of its own.
                result["frames"].append({"piece": id(right[0]), "verb": link["word"], "who": link["who"]})
                return right
            left = self._split(first, depth + 1, result)
            # The link joins the main statement of each side (each side's first).
            link = dict(link)
            link["from"] = id(left[0])
            link["to"] = id(right[0])
            result["links"].append(link)
            return left + right
        return [{"words": self._clean(seq)}]

    @staticmethod
    def _clean(seq: Sequence[Dict[str, Any]]) -> List[Dict[str, Any]]:
        out = list(seq)
        while out and out[0].get("kind") == "punctuation":
            out.pop(0)
        while out and out[-1].get("kind") == "punctuation" and _word(out[-1]) in (",", ";"):
            out.pop()
        return out

    def _leading_condition(self, seq: List[Dict[str, Any]]):
        """"When I was a kid(,) I lived in Ohio", "if it rains we stay home",
        "because she worked late, she was tired": the main statement comes
        first, then the one saying when / if / why."""
        word = _word(seq[0])
        if word not in SUBORDINATORS:
            return None
        rest = seq[1:]
        if not self._starts_statement(rest):
            return None  # "after dinner we left": not a statement after it (handled as a phrase)
        commas = [i for i, e in enumerate(rest) if e.get("kind") == "punctuation" and _word(e) == ","]
        cut = None
        if commas and self._starts_statement(rest[commas[0] + 1:]):
            cut = commas[0]
            condition, main = rest[:cut], rest[cut + 1:]
        else:
            # No comma: where does the first statement end? Every place where the
            # rest starts a statement of its own; the shapes she knows decide.
            first_verb = self._subject_end(rest) or 0
            options = []
            for k in range(first_verb + 1, len(rest)):
                if self._starts_statement(rest[k:]) and rest[k].get("kind") in _NOMINAL:
                    a, b = rest[:k], rest[k:]
                    # The condition is one statement: no second one inside it
                    # ("when I was a kid | I lived in Ohio but now I live...").
                    if any(_word(e) in COORDINATORS | SUBORDINATORS for e in a) or any(
                            self._starts_statement(a[x:]) and a[x].get("kind") in _NOMINAL
                            for x in range(first_verb + 1, len(a))):
                        continue
                    options.append((k, -(self.shapes.seen(a) + self.shapes.seen(b)), a, b))
            if not options:
                return None
            # Where the pieces have shapes she has seen most; the first place it can end among equals.
            options.sort(key=lambda o: (o[1], o[0]))
            cut, _, condition, main = options[0]
        kind = {"because": "why", "since": "why", "if": "on_condition", "unless": "unless",
                "although": "despite", "though": "despite", "whereas": "despite"}.get(word, "when")
        return main, condition, {"word": word, "kind": kind}

    def _joined(self, seq: List[Dict[str, Any]]):
        """Two statements joined in the middle: "I got a new job and I am so
        happy", "she was tired because she worked late", "my sister and I went
        to the store and bought apples" (the second shares the subject)."""
        for i in range(1, len(seq) - 1):
            word = _word(seq[i])
            if word not in COORDINATORS | SUBORDINATORS:
                continue
            left, right = self._clean(seq[:i]), self._clean(seq[i + 1:])
            if not left or not right or not self._has_verb(left) or not self._has_verb(right):
                continue
            if self._subject_end(left) is None and not self._has_verb(left):
                continue
            if self._starts_statement(right):
                kind = "and" if word in COORDINATORS else (
                    {"because": "why", "since": "why", "if": "on_condition", "unless": "unless",
                     "although": "despite", "though": "despite", "whereas": "despite"}.get(word, "when"))
                return left, right, {"word": word, "kind": word if word in COORDINATORS else kind}
            if word in COORDINATORS and _is_verbish(right[0]):
                # "... and bought some apples": the same subject did the second thing.
                subject = self._subject_of(left)
                if subject:
                    return left, subject + right, {"word": word, "kind": word, "shared_subject": True}
        return None

    def _relative(self, seq: List[Dict[str, Any]]):
        """"The dog that my sister owns is very loud" -> "the dog is very loud"
        and "my sister owns the dog". "The man who lives next door is nice" ->
        "the man is nice" and "the man lives next door"."""
        for j in range(1, len(seq) - 1):
            if _word(seq[j]) not in RELATIVES or seq[j - 1].get("kind") not in ("noun", "proper_noun"):
                continue
            start = j - 1
            while start > 0 and seq[start - 1].get("kind") in ("adjective", "determiner", "possessive", "number"):
                start -= 1
            thing = list(seq[start:j])
            body = seq[j + 1:]
            if not body:
                continue
            if _is_verbish(body[0]):
                own_verb = 0  # "who lives next door": the thing does it
            else:
                own_verb = self._subject_end(body)  # "that my sister owns": done to the thing
                if own_verb is None:
                    continue
            # The statement about the thing ends where the sentence's own verb
            # comes back ("... owns | is very loud").
            end = len(body)
            for k in range(own_verb + 1, len(body)):
                if _is_verbish(body[k]) and (not _is_verbish(body[k - 1]) or body[k - 1].get("kind") == "verb"):
                    end = k
                    break
            inner = body[:end]
            about = (thing + inner) if own_verb == 0 else (inner + thing)
            main = list(seq[:j]) + list(body[end:])
            if not self._has_verb(main) or not self._has_verb(about):
                continue
            return main, about, {"word": _word(seq[j]), "kind": "about_thing", "thing": [str(e.get("surface")) for e in thing]}
        return None

    def _what_someone_thinks(self, seq: List[Dict[str, Any]]):
        """"I think (that) you are getting better", "she said she was tired":
        the statement thought or said, with who holds it."""
        subject_end = self._subject_end(seq)
        if subject_end is None:
            return None
        verb = subject_end
        while verb < len(seq) - 1 and seq[verb].get("kind") in ("auxiliary", "modal", "negation") \
                and (_is_verbish(seq[verb + 1]) or seq[verb + 1].get("kind") == "negation"):
            verb += 1  # "don't think", "would say": the helper, then the verb
        if seq[verb].get("kind") != "verb":
            return None
        after = seq[verb + 1:]
        if after and _word(after[0]) == "that":
            after = after[1:]
        elif not (after and after[0].get("kind") == "pronoun" and _word(after[0]) not in _OBJECT_PRONOUNS):
            return None
        if not self._starts_statement(after):
            return None
        frame = list(seq[:verb + 1])
        return frame, after, {"word": str(seq[verb].get("lemma") or seq[verb].get("surface")),
                              "kind": "held_by", "who": [str(e.get("surface")) for e in seq[:subject_end]]}


def words_of(piece: Dict[str, Any], surfaces: Optional[Sequence[str]] = None) -> str:
    """A piece's words as text, keeping the original spelling (names)."""
    out = []
    for entry in piece["words"]:
        idx = entry.get("index")
        word = surfaces[idx] if surfaces is not None and isinstance(idx, int) and idx < len(surfaces) \
            else str(entry.get("surface") or "")
        out.append(word)
    text = " ".join(out)
    for mark in (" ,", " .", " !", " ?", " ;", " '"):
        text = text.replace(mark, mark.strip())
    return text.strip()


__all__ = ["SentenceStructure", "ShapeMemory", "words_of", "COORDINATORS", "SUBORDINATORS", "RELATIVES"]
