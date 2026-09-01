# Test for MetaCognitionLobe
from meta_cognition_lobe import MetaCognitionLobe

def test_meta_cognition_lobe():
    lobe = MetaCognitionLobe()
    lobe.assess_self({'confidence': 0.9})
    assert lobe.self_state['confidence'] == 0.9, f"Unexpected self_state: {lobe.self_state}"
    lobe.detect_error('test_error')
    assert 'test_error' in lobe.error_log, f"Error not logged: {lobe.error_log}"
    lobe.reset()
    print('MetaCognitionLobe OK')

if __name__ == "__main__":
    test_meta_cognition_lobe()
