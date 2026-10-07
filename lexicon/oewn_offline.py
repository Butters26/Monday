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


def _related_lemmas(surface: str) -> set:
    """Surface + Morphy/wn lemma candidates (angry→angry, worried→worry)."""
    form = (surface or "").strip().lower()
    out = {form} if form else set()
    if not form:
        return out
    try:
        for cand in lemma_and_pos_candidates(form):
            lem = str(cand.get("lemma") or "").strip().lower()
            if lem:
                out.add(lem)
    except Exception:
        pass
    return out


def _noun_reaches_emotion(synset, *, max_depth: int = 8) -> bool:
    stack = [(synset, 0)]
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
    return False


def sense_is_affective(
    synset_id: str = "",
    definition: str = "",
    *,
    surface: str = "",
    max_depth: int = 8,
) -> bool:
    """True when an OEWN sense reaches emotion/feeling via real relations.

    Walk (no gloss substring lists, no handmade angry/furious bags):
      - nouns: hypernyms to emotion/feeling
      - verbs: hypernyms + sense-level derivation → noun → hypernyms
      - adjectives (a/s):
          * direct attribute → noun → hypernyms
          * sense-level derivation for THIS surface lemma only
            (skip sister lemmas on the same synset — dread on awful.s)
          * one-hop similar neighbor: that neighbor's own derivations
            (irate → angry → anger.n). Neighbor attributes alone do NOT
            transfer (blocks awful≈terror via alarming.attribute).

    Optional ``surface`` scopes derivation to the word being judged.
    The ``definition`` argument is ignored (call-site compatibility).

    FAIL history:
      - b8ef040: _AFFECT_DEF_MARKERS gloss substrings
      - bd4d5fb: stamped PASS on angry/furious NOT counting as affect
    """
    del definition  # taxonomy/relations only — never read gloss text
    sid = (synset_id or "").strip()
    if not sid:
        return False
    related = _related_lemmas(surface)
    try:
        wnet = get_wordnet()
        try:
            syn = wnet.synset(sid)
        except Exception:
            return False
        # origin: "self" = starting synset / attribute targets;
        #         "neighbor" = one-hop similar (derivation only, no attribute inherit)
        stack = [(syn, 0, "self")]
        seen = set()
        while stack:
            node, depth, origin = stack.pop()
            nid = str(node.id)
            key = (nid, origin)
            if key in seen or depth > max_depth:
                continue
            seen.add(key)
            if nid in _AFFECT_ROOT_IDS:
                return True
            try:
                for hyp in node.hypernyms():
                    stack.append((hyp, depth + 1, origin))
            except Exception:
                pass
            pos = str(getattr(node, "pos", "") or "")
            if pos in {"a", "s"}:
                if origin == "self":
                    try:
                        for related_syn in node.get_related("attribute"):
                            stack.append((related_syn, depth + 1, "self"))
                    except Exception:
                        pass
                try:
                    for sense in node.senses():
                        try:
                            lem = str(sense.word().lemma()).lower()
                        except Exception:
                            continue
                        # Self synset: only this surface's lemmas (not dread on awful).
                        # Similar neighbor: any lemma of that neighbor adjective.
                        if origin == "self" and related and lem not in related:
                            continue
                        try:
                            for derived in sense.get_related("derivation"):
                                stack.append((derived.synset(), depth + 1, "self"))
                        except Exception:
                            pass
                except Exception:
                    pass
                if origin == "self":
                    try:
                        for neigh in node.get_related("similar"):
                            stack.append((neigh, depth + 1, "neighbor"))
                    except Exception:
                        pass
            elif pos == "v":
                try:
                    for sense in node.senses():
                        try:
                            lem = str(sense.word().lemma()).lower()
                        except Exception:
                            continue
                        if related and lem not in related:
                            continue
                        try:
                            for derived in sense.get_related("derivation"):
                                stack.append((derived.synset(), depth + 1, "self"))
                        except Exception:
                            pass
                except Exception:
                    pass
    except Exception:
        return False
    return False


def surface_is_affective(surface: str, *, max_depth: int = 8) -> bool:
    """Affect for a surface form via OEWN senses + lemma→noun/verb bridges.

    Bridge (when adj links are thin, e.g. worried): Morphy/wn lemma candidates
    → noun synsets (hypernyms) or verb synsets (derivation) reaching emotion.
    Not a word list.
    """
    form = (surface or "").strip()
    if not form or not any(ch.isalpha() for ch in form):
        return False
    for sense in lookup_senses(form):
        if sense_is_affective(
            str(sense.get("synset_id") or ""),
            str(sense.get("definition") or ""),
            surface=form,
            max_depth=max_depth,
        ):
            return True
    try:
        wnet = get_wordnet()
    except Exception:
        return False
    for lem in _related_lemmas(form):
        try:
            for syn in wnet.synsets(lem, pos="n"):
                if _noun_reaches_emotion(syn, max_depth=max_depth):
                    return True
        except Exception:
            pass
        try:
            for syn in wnet.synsets(lem, pos="v"):
                if sense_is_affective(str(syn.id), surface=lem, max_depth=max_depth):
                    return True
        except Exception:
            pass
    return False


# ---------------------------------------------------------------------------
# Same-kind claim keys for cross-turn correction (Conversation).
# OEWN graph only — no handmade lemma bags (shape/form/trait/artifact/…).
# ---------------------------------------------------------------------------

# OEWN unique taxonomy root (the noun synset with no hypernyms).
_ENTITY_SYNSET_ID = "oewn-00001740-n"

# Hypernyms shallower than this depth-from-entity are too generic to mark
# same-kind. depth 0 = entity; depth 1 = physical entity / abstraction tops.
# depth 2 (matter, relation, object, …) MAY anchor compete keys — required so
# brass∩plastic (LCS=matter) counts as material replace. Honest: this is a
# structural depth rule, not a lemma list; broad depth-2 nodes can still
# over-match (e.g. aluminum vs hotdog-sense dog via matter).
_TRIVIAL_MAX_ENTITY_DEPTH = 2  # trivial iff depth_from_entity < this


@lru_cache(maxsize=8192)
def _synset_depth_from_entity(synset_id: str) -> Optional[int]:
    """Shortest hypernym-walk distance from synset up to OEWN entity root."""
    sid = (synset_id or "").strip()
    if not sid:
        return None
    try:
        wnet = get_wordnet()
        syn = wnet.synset(sid)
    except Exception:
        return None
    stack = [(syn, 0)]
    seen = set()
    best: Optional[int] = None
    while stack:
        node, depth = stack.pop()
        nid = str(node.id)
        if nid in seen:
            continue
        seen.add(nid)
        if nid == _ENTITY_SYNSET_ID:
            best = depth if best is None else min(best, depth)
            continue
        try:
            for hyp in node.hypernyms():
                stack.append((hyp, depth + 1))
        except Exception:
            pass
    return best


def _hypernym_is_trivial(synset) -> bool:
    """True when a noun hypernym is too close to the OEWN entity root.

    Structural OEWN rule: depth_from_entity < _TRIVIAL_MAX_ENTITY_DEPTH.
    Not a handmade lemma frozenset.
    """
    if synset is None:
        return True
    if str(getattr(synset, "pos", "") or "") != "n":
        return True
    depth = _synset_depth_from_entity(str(synset.id))
    if depth is None:
        return True
    return depth < _TRIVIAL_MAX_ENTITY_DEPTH


def complement_compete_keys(
    surface: str,
    senses: Optional[List[Dict[str, Any]]] = None,
    *,
    kind: Optional[str] = None,
    max_hyp_depth: int = 6,
    max_similar_hops: int = 2,
) -> List[str]:
    """OEWN keys that identify the claim-dimension of a predicative complement.

    Keys are stable strings Conversation can intersect across turns:
      hyp:<synset>   non-trivial noun hypernym
      attr:<synset>  adjective attribute noun
      der:<synset>   surface-scoped derivation noun (+ non-trivial hypernyms)
      sim:<synset>   similar_to / antonym cluster member
      ant:<lemma>    antonym lemma

    ``kind`` is Language's predicative_complement kind (nominal / adjective).
    Uses senses already on the packet when provided — does not invent banks.
    Non-trivial hypernyms: OEWN depth-from-entity >= 2 (see _hypernym_is_trivial).
    Not a handmade lemma bag.
    """
    form = (surface or "").strip()
    sense_list = list(senses or [])
    if not sense_list and form:
        if kind == "nominal":
            sense_list = lookup_senses(form, pos="n", max_senses=6)
        elif kind == "adjective":
            seen_ids = set()
            merged: List[Dict[str, Any]] = []
            for pos in ("a", "s"):
                for s in lookup_senses(form, pos=pos, max_senses=6):
                    sid = str(s.get("synset_id") or "")
                    if sid and sid not in seen_ids:
                        seen_ids.add(sid)
                        merged.append(s)
            sense_list = merged[:8]
        else:
            sense_list = lookup_senses(form, max_senses=6)
    if not sense_list:
        return []

    related = _related_lemmas(form)
    keys: set = set()
    try:
        wnet = get_wordnet()
    except Exception:
        return []

    for sense in sense_list:
        sid = str(sense.get("synset_id") or "").strip()
        if not sid:
            continue
        try:
            syn = wnet.synset(sid)
        except Exception:
            continue
        pos = str(getattr(syn, "pos", "") or sense.get("pos") or "")
        if kind == "nominal" and pos != "n":
            continue
        if kind == "adjective" and pos not in {"a", "s"}:
            continue

        if pos == "n":
            stack = [(syn, 0)]
            seen = set()
            while stack:
                node, depth = stack.pop()
                nid = str(node.id)
                if nid in seen or depth > max_hyp_depth:
                    continue
                seen.add(nid)
                if depth > 0 and not _hypernym_is_trivial(node):
                    keys.add(f"hyp:{nid}")
                try:
                    for hyp in node.hypernyms():
                        stack.append((hyp, depth + 1))
                except Exception:
                    pass

        if pos in {"a", "s"}:
            stack = [(syn, 0)]
            seen = set()
            while stack:
                node, depth = stack.pop()
                nid = str(node.id)
                if nid in seen or depth > max_similar_hops:
                    continue
                seen.add(nid)
                keys.add(f"sim:{nid}")
                try:
                    for attr in node.get_related("attribute"):
                        if not _hypernym_is_trivial(attr):
                            keys.add(f"attr:{attr.id}")
                except Exception:
                    pass
                try:
                    for neigh in node.get_related("similar"):
                        stack.append((neigh, depth + 1))
                except Exception:
                    pass
                try:
                    for sense_obj in node.senses():
                        for rel in sense_obj.get_related("antonym"):
                            try:
                                keys.add(f"ant:{str(rel.word().lemma()).lower()}")
                                stack.append((rel.synset(), depth + 1))
                            except Exception:
                                pass
                except Exception:
                    pass

            # Surface-scoped derivation on THIS synset only (not sister lemmas).
            try:
                for sense_obj in syn.senses():
                    try:
                        lem = str(sense_obj.word().lemma()).lower()
                    except Exception:
                        continue
                    if related and lem not in related:
                        continue
                    try:
                        for rel in sense_obj.get_related("derivation"):
                            dsyn = rel.synset()
                            if str(getattr(dsyn, "pos", "")) != "n":
                                continue
                            # Derived noun + immediate hypernym only.
                            # Deeper walks (looseness→…→quality) false-match
                            # unrelated adjectives on the evaluative scale.
                            hstack = [(dsyn, 0)]
                            hseen = set()
                            while hstack:
                                hn, hd = hstack.pop()
                                hid = str(hn.id)
                                if hid in hseen or hd > 1:
                                    continue
                                hseen.add(hid)
                                if not _hypernym_is_trivial(hn):
                                    keys.add(f"der:{hid}")
                                try:
                                    for hh in hn.hypernyms():
                                        hstack.append((hh, hd + 1))
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except Exception:
                pass

            # One-hop similar HEAD adjectives (pos=a): attributes + derivations.
            # Bridges satellites (fine→satisfactory→quality, awful→bad→quality)
            # without walking every sister satellite's obscure senses.
            try:
                for neigh in syn.get_related("similar"):
                    if str(getattr(neigh, "pos", "")) != "a":
                        continue
                    try:
                        for attr in neigh.get_related("attribute"):
                            if not _hypernym_is_trivial(attr):
                                keys.add(f"attr:{attr.id}")
                    except Exception:
                        pass
                    try:
                        for sense_obj in neigh.senses():
                            for rel in sense_obj.get_related("derivation"):
                                dsyn = rel.synset()
                                if str(getattr(dsyn, "pos", "")) != "n":
                                    continue
                                if not _hypernym_is_trivial(dsyn):
                                    keys.add(f"der:{dsyn.id}")
                                try:
                                    for hh in dsyn.hypernyms():
                                        if not _hypernym_is_trivial(hh):
                                            keys.add(f"der:{hh.id}")
                                except Exception:
                                    pass
                    except Exception:
                        pass
            except Exception:
                pass

    return sorted(keys)


def complements_compete(
    prev_complement: Optional[Dict[str, Any]],
    curr_complement: Optional[Dict[str, Any]],
) -> bool:
    """True when two predicative complements are competing values of one claim kind.

    Same Language ``kind`` (nominal vs adjective) required. Then OEWN compete
    keys must intersect, or one lemma is an antonym key of the other.
    Different kinds (material noun vs shape adjective) never compete.
    """
    if not isinstance(prev_complement, dict) or not isinstance(curr_complement, dict):
        return False
    prev_kind = str(prev_complement.get("kind") or "").strip().lower() or None
    curr_kind = str(curr_complement.get("kind") or "").strip().lower() or None
    if prev_kind and curr_kind and prev_kind != curr_kind:
        return False

    prev_lemma = str(
        prev_complement.get("lemma") or prev_complement.get("surface") or ""
    ).strip().lower()
    curr_lemma = str(
        curr_complement.get("lemma") or curr_complement.get("surface") or ""
    ).strip().lower()
    if not prev_lemma or not curr_lemma or prev_lemma == curr_lemma:
        return False

    prev_keys = prev_complement.get("compete_keys")
    if not isinstance(prev_keys, list) or not prev_keys:
        prev_keys = complement_compete_keys(
            prev_lemma,
            prev_complement.get("senses")
            if isinstance(prev_complement.get("senses"), list)
            else None,
            kind=prev_kind,
        )
    curr_keys = curr_complement.get("compete_keys")
    if not isinstance(curr_keys, list) or not curr_keys:
        curr_keys = complement_compete_keys(
            curr_lemma,
            curr_complement.get("senses")
            if isinstance(curr_complement.get("senses"), list)
            else None,
            kind=curr_kind,
        )

    prev_set = {str(k) for k in prev_keys}
    curr_set = {str(k) for k in curr_keys}
    if prev_set & curr_set:
        return True
    if f"ant:{curr_lemma}" in prev_set or f"ant:{prev_lemma}" in curr_set:
        return True
    return False


__all__ = [
    "OfflineLexiconError",
    "complement_compete_keys",
    "complements_compete",
    "ensure_oewn",
    "get_wordnet",
    "lemma_and_pos_candidates",
    "lexicon_paths",
    "lookup_senses",
    "sense_is_affective",
    "surface_is_affective",
]
