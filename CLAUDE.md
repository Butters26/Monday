# Instructions for Claude working on Monday

## Matthew's rule: how to check Monday works

Checking whether Monday works means **booting her up, using her, and reading what the live tracer recorded.** A test score is not proof.

1. Start her the way Matthew would, with the tracer on:
   `MONDAY_TRACE=1 python _monday_chat_daemon.py` (then `python _monday_say.py "<message>"`), or `MONDAY_TRACE=1 python run_abin.py`.
2. Talk to her about whatever you changed.
3. Read the trace: `python trace_report.py <trace.jsonl>`. It shows her replies and why any reply was blank, crashed turns, messages a lobe didn't understand or never answered, uncaught errors, and printed warnings.
4. Report what the trace shows, failures included. Never say something works because tests passed or because it should work.

The pytest files may be run to catch breakage, but passing tests never prove she works. No PASS/FAIL scoring gates.
