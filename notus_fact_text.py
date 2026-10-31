"""Fact text helpers for Notus memory.

Pulls durable personal facts out of a sentence ("My name is Matthew" ->
user / name / Matthew), formats stored facts back into sentences, and scores
how well a question matches stored text.

Moved verbatim out of notus_memory.py (the PostgreSQL memory) so the live
SQLite memory in direct_notus.py no longer depends on PostgreSQL code or the
psycopg2 library.
"""

from __future__ import annotations

import re


class FactText:
    """Stateless fact extraction, formatting, and match-scoring helpers."""

    _RETRIEVAL_STOPWORDS = frozenset(
        {
            "a", "an", "the", "is", "are", "was", "were", "be", "been", "am",
            "i", "my", "me", "mine", "you", "your", "yours", "we", "our",
            "what", "whats", "who", "whom", "where", "when", "why", "how",
            "do", "does", "did", "can", "could", "would", "should", "please",
            "remember", "that", "this", "these", "those", "with", "from",
            "about", "tell", "of", "to", "in", "on", "at", "for", "and", "or",
            "it", "its", "have", "has", "had", "will", "just", "also", "so",
            "as", "if", "but", "not", "no", "yes", "ok", "okay", "hey", "hi",
            "hello", "got", "know", "which", "whose",
            "now", "currently",
            "there", "here", "into", "over", "under", "again", "any", "some",
        }
    )
    # Durable identity tokens must survive stopword stripping on BOTH query and
    # content sides — otherwise "What is my name?" yields empty tokens and the
    # name predicate can never match "Your name is Matthew."
    _RETRIEVAL_KEEPWORDS = frozenset({"name", "named", "called"})
    # Ask-verbs / fillers that must not AND-gate identity recall
    # ("remind me my name", "what am I called name").
    _WEAK_QUERY_TOKENS = frozenset(
        {
            "remind", "call", "tell", "please", "know", "said", "say",
            # Speech-recall meta fillers must not AND-gate Monday's own lines
            # ("the thing you said", "exact words", "earlier about…").
            "thing", "things", "word", "words", "exact", "earlier", "before",
            "previously", "phrase", "told", "called", "mention", "mentioned",
        }
    )
    # Minimum share of query content-tokens that must appear in a hit.
    _MIN_RELEVANCE = 0.34
    # Hard cap so pathological corpora stay bounded; still far beyond the old ~50 window.
    _CORPUS_SCAN_CAP = 5000

    _FRAGILE_FACT_NOUNS = frozenset(
        {
            "day", "life", "mood", "feeling", "feelings", "time", "thing",
            "stuff", "question", "answer", "message", "chat", "conversation",
            "thought", "idea", "problem", "issue", "way", "point", "one",
            "friend", "world", "today", "tonight", "morning", "afternoon",
            "evening", "week", "month", "year", "everything", "nothing",
        }
    )
    # Secret/label nouns that are durable even without a leading "my".
    _DURABLE_KEY_NOUNS = frozenset(
        {
            "codeword", "password", "passphrase", "passcode", "pin", "secret",
            "callsign", "codename", "username", "nickname", "alias", "handle",
            "birthday", "hometown", "timezone", "badge", "key", "token",
            "access_code", "access code", "safe word", "safeword",
        }
    )
    _VAGUE_VALUE_PREFIXES = (
        "going", "feeling", "looking", "doing", "getting", "being", "having",
        "trying", "thinking", "wondering", "hoping", "wanting", "needing",
        "really", "just", "kinda", "kind of", "sort of", "pretty",
    )
    # Bidirectional aliases so "job" finds work_as facts / "live" finds lives_in.
    _TOKEN_ALIASES = {
        "job": frozenset({"job", "work", "occupation", "profession"}),
        "work": frozenset({"job", "work", "occupation", "profession"}),
        "occupation": frozenset({"job", "work", "occupation", "profession"}),
        "profession": frozenset({"job", "work", "occupation", "profession"}),
        "live": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "lives": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "living": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "hometown": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "city": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "location": frozenset({"live", "lives", "living", "hometown", "city", "location"}),
        "hike": frozenset({"hike", "hiking", "hiked"}),
        "hiking": frozenset({"hike", "hiking", "hiked"}),
        "hiked": frozenset({"hike", "hiking", "hiked"}),
        # Identity asks: "what am I called" / name predicate / readable "name is".
        # "what am I called" is handled by _augment_identity_query (+ name),
        # not by aliasing everyday "call" onto the name predicate.
        "name": frozenset({"name", "named", "called", "call"}),
        "named": frozenset({"name", "named", "called", "call"}),
        "called": frozenset({"name", "named", "called", "call"}),
        "call": frozenset({"name", "named", "called", "call"}),
    }

    @classmethod
    def _alias_set(cls, token: str) -> set:
        return set(cls._TOKEN_ALIASES.get(token, frozenset())) | {token}

    @classmethod
    def _expand_tokens(cls, tokens: set) -> set:
        out = set(tokens or set())
        for t in list(out):
            out |= cls._alias_set(t)
        return out

    @classmethod
    def _stem_token(cls, w: str) -> str:
        """Light stemming for ranking (possessives, -ing/-ed, simple plurals)."""
        if w.endswith("'s") and len(w) > 3:
            w = w[:-2]
        elif w.endswith("s'") and len(w) > 3:
            w = w[:-2]
        short_ing = {
            "going": "go",
            "being": "be",
            "doing": "do",
            "having": "have",
            "nothing": "nothing",
        }
        irregular = {"called": "call", "named": "name"}
        if w in irregular:
            return irregular[w]
        if w in short_ing:
            return short_ing[w]
        if len(w) > 5 and w.endswith("ing"):
            base = w[:-3]
            if len(base) >= 3 and base[-1] == base[-2] and base[-1] not in "aeiou":
                w = base[:-1]  # running -> run
            else:
                w = base + "e"  # hiking -> hike
        elif len(w) > 4 and w.endswith("ed") and not w.endswith(("eed", "ied")):
            base = w[:-2]
            if len(base) >= 3 and base[-1] == base[-2] and base[-1] not in "aeiou":
                w = base[:-1]
            else:
                w = base + "e" if not base.endswith("e") else base  # hiked -> hike
        # Very light plural fold: dogs->dog, names->name (keep ss/us/is).
        if (
            len(w) > 3
            and w.endswith("s")
            and not w.endswith(("ss", "us", "is", "ous", "ics"))
        ):
            w = w[:-1]
        return w

    @classmethod
    def _content_token_list(cls, text: str) -> list:
        """Ordered content tokens (stemmed) for phrase / AND scoring."""
        import re

        words = re.findall(r"[a-z0-9']+", (text or "").lower())
        out = []
        for w in words:
            w = cls._stem_token(w)
            if len(w) <= 1:
                continue
            if w in cls._RETRIEVAL_STOPWORDS and w not in cls._RETRIEVAL_KEEPWORDS:
                continue
            out.append(w)
        return out

    @classmethod
    def _content_tokens(cls, text: str) -> set:
        return set(cls._content_token_list(text))

    @classmethod
    def _significant_tokens(cls, tokens: set) -> set:
        """Content tokens that count for multi-token AND gates."""
        return {
            t for t in (tokens or set())
            if len(t) >= 4 and t not in cls._WEAK_QUERY_TOKENS
        }

    @classmethod
    def _overlap_score(cls, query_tokens: set, text: str) -> float:
        """Fraction of query tokens covered, counting durable aliases as hits."""
        if not query_tokens:
            return 0.0
        cand = cls._content_tokens(text)
        if not cand:
            return 0.0
        cand_exp = cls._expand_tokens(cand)
        hits = 0
        for qt in query_tokens:
            if cls._alias_set(qt) & cand_exp:
                hits += 1
        return hits / float(len(query_tokens))

    @classmethod
    def _phrase_bonus(cls, query: str, text: str) -> float:
        """Reward contiguous multi-word matches (dog name, favorite color, …)."""
        q = cls._content_token_list(query)
        if len(q) < 2:
            return 0.0
        c = cls._content_token_list(text)
        if len(c) < 2:
            return 0.0
        cset_bigrams = {(c[i], c[i + 1]) for i in range(len(c) - 1)}
        hits = 0
        total = 0
        for i in range(len(q) - 1):
            total += 1
            if (q[i], q[i + 1]) in cset_bigrams:
                hits += 1
        if total == 0:
            return 0.0
        return 0.12 * (hits / float(total))

    @classmethod
    def _augment_identity_query(cls, query: str) -> str:
        """Ensure identity asks keep a retrievable 'name' signal.

        'who am I' has no content tokens after stopword strip; append 'name'
        so recall can hit the name predicate / readable fact line.
        """
        import re

        q = (query or "").strip()
        if not q:
            return q
        if re.search(
            r"(?i)\b(?:"
            r"who\s+am\s+i|"
            r"what(?:'s|s)?\s+am\s+i\s+called|"
            r"what\s+am\s+i\s+called|"
            r"remind\s+me\s+(?:of\s+)?my\s+name|"
            r"what(?:'s|s)?\s+my\s+name|"
            r"what\s+is\s+my\s+name|"
            r"my\s+name"
            r")\b",
            q,
        ):
            # Keepwords already preserve 'name' when present; inject when absent.
            # Always ensure a 'name' token for identity asks — "what am I called"
            # only yields {call}, which must not block the name inject.
            if "name" not in cls._content_tokens(q):
                if not re.search(r"(?i)\bname\b", q):
                    return q + " name"
        # "What's my dog called?" — inject name so dog_name facts score.
        if re.search(r"(?i)\bmy\s+[a-z][a-z ]{0,40}?\s+called\b", q):
            if "name" not in cls._content_tokens(q) and not re.search(r"(?i)\bname\b", q):
                return q + " name"
        return q

    @classmethod
    def extract_personal_fact_triples(cls, text: str):
        """Durable personal facts only — not fragile chatter.

        Keeps name / favorite / named patterns. Also learns codeword/password-
        style ``(the) X is Y`` and remember-taught durable claims. Generic
        ``my X is Y`` only when the noun looks durable and the value is not a
        vague clause.
        """
        import re
        from typing import List, Optional, Tuple

        if not text or not text.strip():
            return []
        t = text.strip()
        out: List[Tuple[str, str, str, Optional[str]]] = []
        seen = set()

        def _slug(noun: str) -> str:
            return re.sub(r"\s+", "_", noun.strip().lower())

        def _value_ok(val: str) -> bool:
            v = (val or "").strip(" .!?")
            if not v or len(v) > 80:
                return False
            if any(v.lower().startswith(p) for p in cls._VAGUE_VALUE_PREFIXES):
                return False
            # Compound-clause bleed: "Boulder and I work as…" / "Matthew and my dog…"
            if re.search(r"\b(?:and\s+(?:i|my|you|we|he|she|they)\b)", v, re.I):
                return False
            if len(v.split()) > 6:
                return False
            if any(ch in v for ch in (",", ";", ":")) and len(v.split()) > 3:
                return False
            return True

        def _noun_ok(noun: str, *, allow_fragile: bool = False) -> bool:
            n = (noun or "").strip().lower()
            if not n or len(n.split()) > 4:
                return False
            # Reject clause bleed through noun groups ("name is Matthew and my dog").
            if re.search(r"\b(?:is|are|was|were|and|or|named)\b", n):
                return False
            if not allow_fragile and n in cls._FRAGILE_FACT_NOUNS:
                return False
            # Reject pronoun / determiner-only leftovers.
            if n in {"the", "a", "an", "this", "that", "it", "he", "she", "they"}:
                return False
            return True

        def _add(sub: str, pred: str, obj: str) -> None:
            key = (sub.lower(), pred.lower(), obj.lower())
            if key in seen or not sub or not pred or not obj:
                return
            if len(obj) > 80:
                return
            seen.add(key)
            out.append((sub, pred, obj, None))

        def _is_durable_key(noun: str) -> bool:
            n = re.sub(r"\s+", " ", (noun or "").strip().lower())
            if n in cls._DURABLE_KEY_NOUNS:
                return True
            if n.replace(" ", "_") in {
                x.replace(" ", "_") for x in cls._DURABLE_KEY_NOUNS
            }:
                return True
            # Exact soft forms only — never substring-match inside a longer phrase.
            return bool(
                re.fullmatch(
                    r"(?:code\s*word|password|pass\s*phrase|pass\s*code|"
                    r"safe\s*word|access\s*code|call\s*sign|code\s*name|"
                    r"secret|pin|token|badge|username|nickname|alias|handle)",
                    n,
                )
            )

        def _clean_noun(noun: str) -> str:
            n = re.sub(r"\s+", " ", (noun or "").strip().lower())
            # Drop leading teaching / determiner junk if a broader pattern caught it.
            n = re.sub(
                r"^(?:please\s+)?(?:remember\s+)?(?:that\s+)?(?:(?:my|the)\s+)+",
                "",
                n,
            ).strip()
            return n

        # my dog's name is Pixel / my dogs name is Pixel (tight noun — no "is"/"and")
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?my\s+"
            r"([a-z]+(?:\s+[a-z]+){0,3})(?:'s|s')\s+name\s+is\s+"
            r"([A-Za-z0-9][\w-]{0,40})\b",
            t,
        ):
            if _noun_ok(m.group(1), allow_fragile=True):
                _add("user", f"{_slug(m.group(1))}_name", m.group(2).strip())

        # my dog is named Pixel (tight noun — no clause bleed)
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?my\s+"
            r"([a-z]+(?:\s+[a-z]+){0,3})\s+is\s+named\s+"
            r"([A-Za-z0-9][\w-]{0,40})\b",
            t,
        ):
            if _noun_ok(m.group(1), allow_fragile=True):
                _add("user", f"{_slug(m.group(1))}_name", m.group(2).strip())

        # my name is Matthew (stop before compound "and …")
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?my\s+name\s+is\s+"
            r"([A-Za-z][\w-]{0,40})(?=\s+and\b|[.!?,]|$)",
            t,
        ):
            _add("user", "name", m.group(1).strip())

        # my favorite color is blue (value stops before compound "and I/my")
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?my\s+"
            r"(favorite\s+[a-z]+(?:\s+[a-z]+){0,3})\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?=\s+and\s+(?:i|my)\b|[.!?]|$)",
            t,
        ):
            val = m.group(2).strip(" .!?")
            if _value_ok(val):
                _add("user", _slug(m.group(1)), val)

        # Codeword / password / passphrase style (with or without "the"/"my").
        # "Remember the codeword is NebulaQuartz" / "codeword is Alpha"
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?(?:remember\s+(?:that\s+)?)?(?:(?:my|the)\s+)?"
            r"(code\s*word|password|pass\s*phrase|pass\s*code|safe\s*word|"
            r"access\s*code|call\s*sign|code\s*name|secret|pin|token|badge|"
            r"username|nickname|alias|handle)\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?:[.!?]|\s*$)",
            t,
        ):
            noun = _clean_noun(m.group(1))
            val = m.group(2).strip(" .!?")
            if noun and _value_ok(val):
                _add("user", _slug(noun), val)

        # Explicit teaching without "my": remember (that) (the) X is Y
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?remember\s+(?:that\s+)?(?:the\s+)?"
            r"([a-z][a-z\s]{0,40}?)\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?:[.!?]|\s*$)",
            t,
        ):
            noun = _clean_noun(m.group(1))
            val = m.group(2).strip(" .!?")
            if not noun or noun.startswith("favorite "):
                continue
            if val.lower().startswith("named "):
                continue
            if not _noun_ok(noun):
                continue
            if not _value_ok(val):
                continue
            _add("user", _slug(noun), val)

        # Explicit teaching: remember my X is Y
        for m in re.finditer(
            r"(?i)\b(?:please\s+)?remember\s+(?:that\s+)?my\s+"
            r"([a-z][a-z\s]{0,40}?)\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?:[.!?]|\s*$)",
            t,
        ):
            noun = m.group(1).strip()
            val = m.group(2).strip(" .!?")
            if noun.lower().startswith("favorite "):
                continue
            if val.lower().startswith("named "):
                continue
            if not _noun_ok(noun):
                continue
            if not _value_ok(val):
                continue
            _add("user", _slug(noun), val)

        # Generic my X is Y — only short durable nouns, concrete values.
        for m in re.finditer(
            r"(?i)\bmy\s+"
            r"([a-z]+(?:\s+[a-z]+){0,3})\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?=\s+and\s+(?:i|my)\b|[.!?]|$)",
            t,
        ):
            noun = m.group(1).strip()
            val = m.group(2).strip(" .!?")
            noun_l = noun.lower()
            if noun_l.startswith("favorite "):
                continue
            if val.lower().startswith("named "):
                continue
            if not _noun_ok(noun):
                continue
            if not _value_ok(val):
                continue
            _add("user", _slug(noun), val)

        # Bare / the X is Y for exact durable key nouns only (no chatter).
        # Uses the specialized key regex above; this only backfills exact set hits
        # that the soft-spaced regex may have missed (e.g. "pin").
        for m in re.finditer(
            r"(?i)\b(?:(?:my|the)\s+)?([a-z][a-z_]{1,40})\s+is\s+"
            r"([A-Za-z0-9][\w\s-]{0,60}?)(?:[.!?]|\s*$)",
            t,
        ):
            noun = _clean_noun(m.group(1))
            val = m.group(2).strip(" .!?")
            if not _is_durable_key(noun):
                continue
            if not _noun_ok(noun):
                continue
            if not _value_ok(val):
                continue
            _add("user", _slug(noun), val)

        # I live in / I work as|at|in — durable location/job.
        # Stop before compound clauses, and before ", not <old>" corrections.
        for m in re.finditer(
            r"(?i)\b(?:no[,\s]+)?(?:please\s+)?(?:remember\s+(?:that\s+)?)?i\s+live\s+in\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s.-]{0,60}?)(?=\s*,\s*not\b|\s+and\s+i\b|[.!?]|$)",
            t,
        ):
            place = m.group(1).strip(" .!?")
            # Drop trailing tense/hedge so "Denver now" -> "Denver".
            place = re.sub(
                r"(?i)\s+\b(?:now|currently|these\s+days|at\s+the\s+moment|"
                r"these\s+days|anymore|again)\s*$",
                "",
                place,
            ).strip(" .!?")
            if place and _value_ok(place):
                _add("user", "lives_in", place)
        for m in re.finditer(
            r"(?i)\b(?:no[,\s]+)?(?:please\s+)?(?:remember\s+(?:that\s+)?)?i\s+work\s+(as|at|in)\s+"
            r"([A-Za-z0-9][A-Za-z0-9\s.-]{0,60}?)(?=\s*,\s*not\b|\s+and\s+i\b|[.!?]|$)",
            t,
        ):
            job = m.group(2).strip(" .!?")
            if job and _value_ok(job):
                _add("user", f"work_{m.group(1).lower()}", job)

        # Third-party durable location: "Pewdiepie moved to Japan in 2022"
        # / "PewDiePie lives in Japan".
        for m in re.finditer(
            r"(?i)\b([A-Z][A-Za-z0-9][\w'-]{1,40})\s+moved\s+to\s+"
            r"([A-Z][A-Za-z0-9][\w\s'-]{0,40}?)(?=\s+in\s+\d{4}\b|[.!?]|$)",
            t,
        ):
            who = m.group(1).strip()
            place = m.group(2).strip(" .!?")
            if who.lower() in {"i", "we", "they", "he", "she", "it", "you"}:
                continue
            if place and _value_ok(place):
                _add(who, "lives_in", place)
        for m in re.finditer(
            r"(?i)\b([A-Z][A-Za-z0-9][\w'-]{1,40})\s+lives\s+in\s+"
            r"([A-Z][A-Za-z0-9][\w\s'-]{0,40}?)(?=\s+now\b|[.!?]|$)",
            t,
        ):
            who = m.group(1).strip()
            place = m.group(2).strip(" .!?")
            if who.lower() in {"i", "we", "they", "he", "she", "it", "you"}:
                continue
            if place and _value_ok(place):
                _add(who, "lives_in", place)

        return out

    @staticmethod
    def format_personal_fact(subject: str, predicate: str, obj: str) -> str:
        """Turn a stored triple into a short, answerable sentence."""
        pred = (predicate or "").strip()
        obj = (obj or "").strip()
        # Facts memory filed from Language's reading of any sentence.
        negated = pred.startswith("not_")
        core = pred[4:] if negated else pred
        if core in ("is", "is_a") or core.startswith("v:"):
            def who(text: str) -> str:
                t = (text or "").strip()
                if t.casefold() == "user":
                    return "you"
                if t.casefold() == "monday":
                    return "Monday"
                if t.casefold().startswith("user's "):
                    return "your " + t[7:]
                return t
            sub = who(subject)
            sub = sub[:1].upper() + sub[1:]
            plural_you = sub in ("You",)
            be = ("are" if plural_you else "is") + (" not" if negated else "")
            if core == "is":
                return f"{sub} {be} {obj}."
            if core == "is_a":
                return f"{sub} {be} {'an' if obj[:1].lower() in 'aeiou' else 'a'} {obj}."
            verb, _, prep = core[2:].partition("@")
            if negated:
                verb = ("do not " if plural_you else "does not ") + verb
            elif not plural_you:
                verb = verb + ("es" if verb.endswith(("s", "x", "z", "ch", "sh", "o")) else "s")
            return f"{sub} {verb} {prep + ' ' if prep else ''}{who(obj)}.".replace("  ", " ")
        if pred.endswith("_name"):
            noun = pred[:-5].replace("_", " ").strip() or "thing"
            return f"Your {noun}'s name is {obj}."
        if pred.startswith("favorite_") or pred.startswith("favourite_"):
            return f"Your {pred.replace('_', ' ')} is {obj}."
        sub_l = (subject or "").strip().lower()
        self_sub = sub_l in {"user", "i", "me", ""}
        if pred == "lives_in":
            if self_sub:
                return f"You live in {obj}."
            return f"{subject} lives in {obj}."
        if pred.startswith("work_"):
            prep = pred[5:] or "as"
            if self_sub:
                return f"You work {prep} {obj}."
            return f"{subject} works {prep} {obj}."
        if self_sub:
            return f"Your {pred.replace('_', ' ')} is {obj}."
        return f"{subject} {pred.replace('_', ' ')} {obj}".strip()
