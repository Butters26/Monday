# Test for ValueGoalManagementLobe
from value_goal_management_lobe import ValueGoalManagementLobe

def test_value_goal_management_lobe():
    lobe = ValueGoalManagementLobe()
    lobe.update_values({'honesty': 10})
    assert lobe.values['honesty'] == 10, f"Unexpected values: {lobe.values}"
    lobe.add_goal('finish_project')
    assert 'finish_project' in lobe.goals, f"Goal not added: {lobe.goals}"
    prioritized = lobe.prioritize_goals()
    assert prioritized == lobe.goals, f"Unexpected prioritized goals: {prioritized}"
    lobe.route_goals()
    lobe.reset()
    print('ValueGoalManagementLobe OK')

if __name__ == "__main__":
    test_value_goal_management_lobe()
