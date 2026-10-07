"""Offline linguistic resources owned by Monday Language."""

from .oewn_offline import (
    OfflineLexiconError,
    complement_compete_keys,
    complements_compete,
    ensure_oewn,
    get_wordnet,
    lookup_senses,
)

__all__ = [
    "OfflineLexiconError",
    "complement_compete_keys",
    "complements_compete",
    "ensure_oewn",
    "get_wordnet",
    "lookup_senses",
]
