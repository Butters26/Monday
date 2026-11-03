"""Old sentence splitter from language_comprehension.py (moved Nov 3, 2026).

Replaced by language_structure.py, which reads the statements in a long
sentence (joined, inside another, about a thing, someone's view) and learns
sentence shapes. Kept for the record; nothing uses it.
"""


class _OldParts:
    def _parts(self, lexical: List[Dict[str, Any]], original: str, joins: List[str]) -> List[str]:
        """A sentence that joins two statements ("I like cats and I hate dogs")
        split into each one. Only where the joining word starts a new subject
        that has its own verb."""
        # Separate sentences ("I am tired. I worked all day.") are separate statements.
        sentences = [x.strip() for x in re.split(r"(?<=[.!?])\s+", original.strip()) if x.strip()]
        if len(sentences) > 1:
            out: List[str] = []
            for sentence in sentences:
                inner = self.analyze(sentence).get("parts") or []
                out += inner or [sentence.rstrip(".!")]
            return out
        words = original.split()
        if len(words) != len([e for e in lexical if e.get("kind") != "punctuation"]) or len(lexical) < 4:
            return []
        content = [e for e in lexical if e.get("kind") != "punctuation"]
        cuts = []
        for i, entry in enumerate(content[:-2]):
            if entry.get("kind") != "conjunction" or i == 0:
                continue
            nxt = content[i + 1]
            if nxt.get("kind") in ("pronoun", "proper_noun", "determiner", "possessive") and any(
                    e.get("kind") in ("verb", "auxiliary", "modal") or self._has_pos(str(e.get("surface")), "v")
                    for e in content[i + 2:]) and any(
                    e.get("kind") in ("verb", "auxiliary", "modal") for e in content[:i]):
                cuts.append(i)
        joins[:] = [str(content[c].get("surface") or "").casefold() for c in cuts]
        if not cuts:
            return []
        parts, start = [], 0
        for cut in cuts:
            parts.append(" ".join(words[start:cut]).strip(" ,"))
            start = cut + 1
        parts.append(" ".join(words[start:]).strip(" ,"))
        return [p for p in parts if p]

