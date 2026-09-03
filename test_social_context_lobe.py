# Test for SocialContextLobe
from social_context_lobe import SocialContextLobe

def test_social_context_lobe():
    lobe = SocialContextLobe()
    lobe.update_context({'location': 'office'})
    assert lobe.context_state['location'] == 'office', f"Unexpected context_state: {lobe.context_state}"
    lobe.process_social_cue('greeting')
    assert 'greeting' in lobe.social_cues, f"Social cue not processed: {lobe.social_cues}"
    lobe.reset()
    print('SocialContextLobe OK')

if __name__ == "__main__":
    test_social_context_lobe()
