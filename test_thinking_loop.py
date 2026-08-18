#!/usr/bin/env python3
"""
Test Thinking Loop - Verify core cognitive cycle works
"""

import time
import sys
from thinking_loop import ThinkingLoop
from thalamus import get_thalamus


def test_thinking_loop():
    """Test the complete thinking loop"""
    print("🧪 Testing Thinking Loop\n")
    
    # Get Thalamus
    thalamus = get_thalamus()
    
    # Create thinking loop
    loop = ThinkingLoop()
    
    print("✅ Thinking Loop created\n")
    
    # Test manual think cycle (don't start continuous loop)
    print("🔄 Running single think cycle...\n")
    
    try:
        # Manually trigger one cycle
        loop._run_think_cycle()
        
        print("\n✅ Think cycle completed")
        
        # Check metrics
        metrics = loop.process_message({'type': 'get_metrics'})
        print(f"\n📊 Metrics: {metrics}")
        
        # Check recent executions
        executions = loop.process_message({'type': 'get_recent_executions', 'limit': 5})
        print(f"\n📜 Recent executions: {len(executions.get('executions', []))} items")
        
        print("\n✅ Thinking Loop test PASSED")
        
    except Exception as e:
        print(f"\n❌ Test FAILED: {e}")
        import traceback
        traceback.print_exc()
        assert False, str(e)


if __name__ == "__main__":
    success = test_thinking_loop()
    sys.exit(0 if success else 1)
