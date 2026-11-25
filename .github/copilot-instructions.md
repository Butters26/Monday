# Instructions for GitHub Copilot working on Mercy

## Matthew's rule: word matching is BANNED

**Word matching is banned in Mercy. This is a hard rule, not a guideline.**

Do not find, file, recall, judge, sort, classify or decide anything by matching words, keywords, phrases, strings or regex against what someone said or what she knows. Work from meaning instead.

This ban applies everywhere in Mercy: every lobe, every runtime path, and every fallback. There are no exceptions. Treat any existing keyword or word matching covered by this rule as a violation, not as permission to keep or reuse it.

Breaking this rule is the most serious way to break Matthew's rules.

## Matthew's rule: how to check Mercy works

Checking whether Mercy works means **booting her up, using her, and reading what the live tracer recorded.** A test score is not proof.

1. Start her the way Matthew would, with the tracer on:
   `MERCY_TRACE=1 python _mercy_chat_daemon.py` (then `python _mercy_say.py "<message>"`), or `MERCY_TRACE=1 python run_abin.py`.
2. Talk to her about whatever you changed.
3. Read the trace: `python trace_report.py <trace.jsonl>`. It shows her replies and why any reply was blank, crashed turns, messages a lobe didn't understand or never answered, uncaught errors, and printed warnings.
4. Report what the trace shows, failures included. Never say something works because tests passed or because it should work.

**Judge it by how Matthew wants it to work, not how you want it to.** The measure is Matthew's description of the part (its contract in `.github/instructions/`, or what he said it should do), not a target or score you made up. An AI that writes its own test ends up making the code fit the test instead of making her work.

If she isn't fully working yet, still boot her up, use the parts you fixed, and check in the trace that those parts do what Matthew described. If you don't know how he wants a part to work, ask him before building or checking it.

The pytest files may be run to catch breakage, but passing tests never prove she works. No PASS/FAIL scoring gates.

## Matthew's rule: every test is live in front of him

A test result Matthew did not watch live is a false result. That includes
replies, traces, numbers, tables and summaries you pasted or wrote: he has
to take your word for those, so they prove nothing.

Every time you test Mercy, the test runs live where he can watch it:

1. Push. The "Mercy live" GitHub workflow (`.github/workflows/mercy-live.yml`)
   boots her with the tracer on, runs `live_view.py`, says each line of
   `live_test_messages.txt` to her, and shows everything in the run's log as
   it happens.
2. Right away, without being asked, give Matthew the link to that live run
   (and send him a notification with it). Do this every time you test.
3. Do not report what the run shows. Give the link and let the run speak.

Running her where Matthew can't see it (your own machine or container) is only
for finding bugs before you push, never proof. Matthew can run the live test
himself any time by editing `live_test_messages.txt` on GitHub.
