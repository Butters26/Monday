# Test for SensoryIntegrationLobe
from sensory_integration_lobe import SensoryIntegrationLobe

def test_sensory_integration_lobe():
    lobe = SensoryIntegrationLobe()
    lobe.integrate_inputs(['sight', 'sound'])
    assert 'sight' in lobe.sensory_buffer and 'sound' in lobe.sensory_buffer, f"Unexpected sensory_buffer: {lobe.sensory_buffer}"
    assert 'sight' in lobe.normalized_signals and 'sound' in lobe.normalized_signals, f"Unexpected normalized_signals: {lobe.normalized_signals}"
    lobe.reset()
    print('SensoryIntegrationLobe OK')

if __name__ == "__main__":
    test_sensory_integration_lobe()
