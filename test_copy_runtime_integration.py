import tempfile
from run_abin import create_core_systems, shutdown_core_systems


def test_copy_real_lobes_execute_together():
    with tempfile.TemporaryDirectory() as tmp:
        systems = create_core_systems(tmp)
        try:
            answer = systems['thalamus'].process_user_input('What is gravity?', user_id='alice')
            assert answer
            assert systems['output'].last_output == answer
            routes = [item['to'] for item in systems['thalamus'].message_routes]
            for required in ('conversation','notus','emotion','reasoning','language','output'):
                assert required in routes
        finally:
            shutdown_core_systems(systems)


def test_copy_pattern_participates_in_normal_processing():
    with tempfile.TemporaryDirectory() as tmp:
        systems = create_core_systems(tmp)
        try:
            systems['thalamus'].process_user_input('alpha beta alpha beta', user_id='alice')
            routes = [item['to'] for item in systems['thalamus'].message_routes]
            assert 'pattern' in routes, routes
        finally:
            shutdown_core_systems(systems)
