# Test for MotorActionLobe
from motor_action_lobe import MotorActionLobe

def test_motor_action_lobe():
    lobe = MotorActionLobe()
    action = lobe.plan_action('move_forward')
    assert isinstance(action, dict), f"Expected action dict, got: {action}"
    assert action.get('intent') == 'move_forward', f"Unexpected action intent: {action.get('intent')}"
    executed = lobe.execute_action()
    assert isinstance(executed, dict) and executed.get('intent') == 'move_forward', f"Unexpected executed action: {executed}"
    lobe.reset()
    print('MotorActionLobe OK')

if __name__ == "__main__":
    test_motor_action_lobe()
