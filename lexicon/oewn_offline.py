#!/usr/bin/env python3
"""Offline Open English WordNet (OEWN) access for Language.

Download once into the Monday tree. Runtime reads only local files — never
reaches the network. Prefer the `wn` package against the local OEWN archive.
"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

_LEXICON_DIR = Path(__file__).resolve().parent
_ARCHIVE = _LEXICON_DIR / "oewn-2024.xml.gz"
_DATA_DIR = _LEXICON_DIR / "wn_data"
_LEXICON_SPEC = "oewn:2024"


class OfflineLexiconError(RuntimeError):
    """Raised when the offline OEWN base is missing or unusable."""


def lexicon_paths() -> Dict[str, Path]:
    return {
        "lexicon_dir": _LEXICON_DIR,
        "archive": _ARCHIVE,
        "data_dir": _DATA_DIR,
        "database": _DATA_DIR / "wn.db",
    }


def _configure_wn(wn_module) -> None:
    # Force every wn call onto Monday's tree — never home ~/.wn_data or network.
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    wn_module.config.data_directory = _DATA_DIR
    # Belt-and-suspenders for child imports.
    os.environ["WN_DATA_DIR"] = str(_DATA_DIR)


def ensure_oewn(*, allow_download: bool = False) -> Path:
    """Ensure local OEWN database exists. Default: offline-only bootstrap.

    If wn.db is missing but oewn-2024.xml.gz is present, add the local archive.
    Network download is refused unless allow_download=True (one-shot install only).
    """
    try:
        import wn
        from wn.morphy import Morphy
    except ImportError as exc:
        raise OfflineLexiconError(
            "Python package 'wn' is required for offline OEWN. "
            "Install with: pip install wn"
        ) from exc

    _configure_wn(wn)
    db_path = _DATA_DIR / "wn.db"
    if db_path.exists():
        # Validate lexicon is loadable.
        try:
            wn.Wordnet(_LEXICON_SPEC, lemmatizer=Morphy())
            return db_path
        except Exception:
            pass

    if _ARCHIVE.exists():
        wn.add(str(_ARCHIVE))
        wn.Wordnet(_LEXICON_SPEC, lemmatizer=Morphy())
        return db_path

    if not allow_download:
        raise OfflineLexiconError(
            f"Offline OEWN missing. Expected archive at {_ARCHIVE} "
            f"or database at {db_path}. Runtime network is forbidden."
        )

    # One-shot install path only (explicit). Never used by Language at analyze time.
    wn.download(_LEXICON_SPEC)
    return db_path


@lru_cache(maxsize=1)
def get_wordnet():
    """Return a cached Wordnet object bound to local OEWN + Morphy."""
    import wn
    from wn.morphy import Morphy

    ensure_oewn(allow_download=False)
    _configure_wn(wn)
    return wn.Wordnet(_LEXICON_SPEC, lemmatizer=Morphy())


def lookup_senses(
    surface: str,
    *,
    pos: Optional[str] = None,
    max_senses: int = 8,
) -> List[Dict[str, Any]]:
    """Look up OEWN senses for a surface form. Empty list = honest unknown.

    Never invents senses. Never hits the network.
    """
    form = (surface or "").strip()
    if not form or not any(ch.isalpha() for ch in form):
        return []

    wnet = get_wordnet()
    synsets = list(wnet.synsets(form, pos=pos) if pos else wnet.synsets(form))
    scored: List[tuple] = []
    form_cf = form.casefold()
    for synset in synsets:
        lemmas = []
        try:
            lemmas = [str(lemma) for lemma in synset.lemmas()]
        except Exception:
            lemmas = []
        definition = synset.definition() or ""
        # Prefer senses whose lemmas match the surface casefold, and common
        # (lowercase lemma) readings over Proper-name OEWN entries.
        lemma_hit = any(str(x).casefold() == form_cf for x in lemmas)
        properish = any(str(x)[:1].isupper() and str(x).casefold() != form_cf for x in lemmas)
        score = (
            0 if lemma_hit else 1,
            1 if properish else 0,
            0 if definition[:1].islower() else 1,
        )
        scored.append(
            (
                score,
                {
                    "synset_id": str(synset.id),
                    "pos": str(synset.pos),
                    "definition": definition,
                    "lemmas": lemmas,
                },
            )
        )
    scored.sort(key=lambda item: item[0])
    return [item[1] for item in scored[:max_senses]]


def lemma_and_pos_candidates(surface: str) -> List[Dict[str, str]]:
    """Return lemma/pos pairs OEWN knows for this surface (via Morphy)."""
    form = (surface or "").strip()
    if not form or not any(ch.isalpha() for ch in form):
        return []
    wnet = get_wordnet()
    words = list(wnet.words(form))
    seen = set()
    out: List[Dict[str, str]] = []
    for word in words:
        key = (str(word.lemma()), str(word.pos))
        if key in seen:
            continue
        seen.add(key)
        out.append({"lemma": key[0], "pos": key[1]})
    return out


# OEWN taxonomy roots for affective meaning (lexicon ontology only).
# emotion.n.01 / feeling.n.01 — never definition substring lists.
_AFFECT_ROOT_IDS = frozenset(
    {
        "oewn-07495208-n",  # emotion
        "oewn-00026390-n",  # feeling
    }
)


def sense_is_affective(synset_id: str = "", definition: str = "", *, max_depth: int = 8) -> bool:
    """True when an OEWN sense reaches emotion/feeling via taxonomy only.

    Walk:
      - nouns/verbs: hypernyms
      - adjectives (a/s): similar-to cluster, then attribute → noun, then hypernyms

    The ``definition`` argument is ignored (kept for call-site compatibility).
    No definition substring matching. No handmade angry/furious word lists.
    FAIL history: b8ef040 used _AFFECT_DEF_MARKERS; Matty caught it.
    """
    del definition  # taxonomy only — never read gloss text for this decision
    sid = (synset_id or "").strip()
    if not sid:
        return False
    try:
        wnet = get_wordnet()
        try:
            syn = wnet.synset(sid)
        except Exception:
            return False
        stack = [(syn, 0)]
        seen = set()
        while stack:
            node, depth = stack.pop()
            nid = str(node.id)
            if nid in seen or depth > max_depth:
                continue
            seen.add(nid)
            if nid in _AFFECT_ROOT_IDS:
                return True
            try:
                for hyp in node.hypernyms():
                    stack.append((hyp, depth + 1))
            except Exception:
                pass
            pos = str(getattr(node, "pos", "") or "")
            if pos in {"a", "s"}:
                for rel in ("similar", "attribute"):
                    try:
                        for related in node.get_related(rel):
                            stack.append((related, depth + 1))
                    except Exception:
                        pass
    except Exception:
        return False
    return False


__all__ = [
    "OfflineLexiconError",
    "ensure_oewn",
    "get_wordnet",
    "lemma_and_pos_candidates",
    "lexicon_paths",
    "lookup_senses",
    "sense_is_affective",
]
