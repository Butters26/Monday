"""Offline linguistic resources owned by Monday Language."""

from .oewn_offline import ensure_oewn, get_wordnet, lookup_senses, OfflineLexiconError

__all__ = [
    "ensure_oewn",
    "get_wordnet",
    "lookup_senses",
    "OfflineLexiconError",
]
