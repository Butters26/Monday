#!/usr/bin/env python3
"""
Test Thinking Loop - Verify core cognitive cycle works
"""

import sys
from thalamus import get_thalamus
from thinking_loop import ThinkingLoop


def test_thinking_loop():
    """Test the complete thinking loop."""
    thalamus = get_thalamus()
    loop = ThinkingLoop()
    cycle = loop._run_think_cycle()
    assert cycle.get("status") == "success"
    metrics = loop.process_message({'type': 'get_metrics'})
    assert metrics.get("status") == "success"
    assert metrics.get("metrics", {}).get("cycles", 0) >= 1
    executions = loop.process_message({'type': 'get_recent_executions', 'limit': 5})
    assert executions.get("status") == "success"
    assert len(executions.get("executions", [])) >= 1


if __name__ == "__main__":
    test_thinking_loop()
    sys.exit(0)
