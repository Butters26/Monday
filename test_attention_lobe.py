# Test for AttentionLobe
from attention_lobe import AttentionLobe

def test_attention_lobe():
    lobe = AttentionLobe()
    lobe.update_salience(['signal1', 'signal2'])
    focus = lobe.select_focus()
    assert focus in ['signal1', 'signal2'], f"Unexpected focus: {focus}"
    lobe.route_focus()
    lobe.reset()
    print('AttentionLobe OK')

if __name__ == "__main__":
    test_attention_lobe()
