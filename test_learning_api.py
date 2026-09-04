from learning.api import learning_overview, list_lobe_skills, teach_lobe_skill, teach_monday
from run_abin import create_core_systems, shutdown_core_systems


def test_learning_api_wrappers_cover_global_and_targeted_training(tmp_path):
    systems = create_core_systems(str(tmp_path / "runtime"))
    try:
        thalamus = systems["thalamus"]

        global_teach = teach_monday(
            thalamus,
            lesson="Learn grammar and clearer sentence structure.",
            user_id="alice",
        )
        assert global_teach["status"] == "success"
        assert global_teach.get("taught")

        targeted = teach_lobe_skill(
            thalamus,
            lobe="reasoning",
            skill="math_patterns",
            behavior="Detect arithmetic relationships from user text.",
            user_id="alice",
        )
        assert targeted["status"] == "success"

        skills = list_lobe_skills(thalamus, lobe="reasoning", user_id="alice")
        assert skills["status"] == "success"
        assert any(skill.get("key") == "skill:math_patterns" for skill in skills.get("memories", []))

        overview = learning_overview(thalamus, user_id="alice", limit=10)
        assert overview["status"] == "success"
        assert any(row.get("lobe") == "reasoning" for row in overview.get("lobes", []))
    finally:
        shutdown_core_systems(systems)
