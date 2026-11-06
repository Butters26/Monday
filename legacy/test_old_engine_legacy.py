"""Test of the old reasoning engine (moved Nov 6, 2026 with the engine). Not run."""

def test_full_reasoner_think_about_runs_for_every_direct_prompt(tmp_path):
    class SpyFullReasoner(MaximumSophisticationReasoning):
        calls = []

        def think_about(self, input_data):
            type(self).calls.append(input_data)
            return super().think_about(input_data)

    SpyFullReasoner.calls = []
    systems = _boot(tmp_path, reasoning_factory=SpyFullReasoner)
    try:
        systems["thalamus"].process_user_input("hello")
        systems["thalamus"].process_user_input("What is gravity?")
        assert len(SpyFullReasoner.calls) == 2
        assert all(call["user_id"] == "default" for call in SpyFullReasoner.calls)
        assert all(
            call["memory_result"]["status"] == "success"
            for call in SpyFullReasoner.calls
        )
    finally:
        shutdown_core_systems(systems)

