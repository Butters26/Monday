"""Final active Notus memory lobe.

This layer disables the old editor/vocabulary bootstrap behavior inherited from
historical Notus. The active lobe is memory only; it does not seed writing rules
or language behavior into its database.
"""

from notus_memory import NotusMemorySystem


class ActiveNotusMemorySystem(NotusMemorySystem):
    """Memory-only Notus used by run_abin (PostgreSQL primary).

    Inherits legacy SuperhumanMemorySystem naming in the stack; live status
    reports embedding_model_type via _embedding_honesty(). Hash/basic mode is
    not sold as semantic understanding.
    """

    def _init_database(self) -> None:
        # Let the historical memory engine create its PostgreSQL schema first.
        super()._init_database()

        # Add the memory-integrity fields before anything can use remember_fact.
        self._ensure_memory_integrity_schema()

        # Historical Notus created brain_facts.created_at as TEXT but
        # last_reinforced as TIMESTAMP. PostgreSQL cannot COALESCE those two
        # different types during recall, so normalize both columns here.
        with self._db_connection.cursor() as cursor:
            cursor.execute(
                "ALTER TABLE brain_facts "
                "ALTER COLUMN created_at TYPE TIMESTAMP "
                "USING created_at::timestamp"
            )
            cursor.execute(
                "ALTER TABLE brain_facts "
                "ALTER COLUMN last_reinforced TYPE TIMESTAMP "
                "USING last_reinforced::timestamp"
            )
        self._db_connection.commit()

    def _seed_editor_knowledge(self, user_id: str = "default") -> None:
        return None

    def _seed_vocabulary_and_grammar(self) -> None:
        return None
