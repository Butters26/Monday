"""Final active Notus memory lobe.

This layer disables the old editor/vocabulary bootstrap behavior inherited from
historical Notus. The active lobe is memory only; it does not seed writing rules
or language behavior into its database.
"""

from notus_memory import NotusMemorySystem


class ActiveNotusMemorySystem(NotusMemorySystem):
    """Memory-only Notus used by run_abin."""

    def _seed_editor_knowledge(self, user_id: str = "default") -> None:
        return None

    def _seed_vocabulary_and_grammar(self) -> None:
        return None
