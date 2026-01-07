# Test for ExecutiveControlLobe
from executive_control_lobe import ExecutiveControlLobe

def test_executive_control_lobe():
    lobe = ExecutiveControlLobe()
    lobe.add_task('do_something')
    assert lobe.task_list == ['do_something'], f"Unexpected task list: {lobe.task_list}"
    executed = lobe.execute_next_task()
    assert executed == 'do_something', f"Unexpected executed task: {executed}"
    lobe.set_inhibition(True)
    assert lobe.execute_next_task() is None, "Inhibition failed"
    lobe.reset()
    print('ExecutiveControlLobe OK')

if __name__ == "__main__":
    test_executive_control_lobe()
