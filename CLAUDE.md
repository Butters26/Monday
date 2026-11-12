# Instructions for Claude working on Monday

## LAW: You do not get to define "100%" or "working". Matthew does.

This overrides everything else. It applies to every AI and every session.

1. **"Works", "done", "fixed", "100%" mean one thing only: it does what Matthew's contract for that part says** (`.github/instructions/<part>.instructions.md`), or what Matthew said in so many words. Never your own idea of what it should do.
2. **You may not make up test sentences or expected answers and count them as proof.** Test with what Matthew gave you or what his contract says, quoted. If you try something of your own to look for bugs, say plainly "this is my test, not Matthew's" and never count it toward a percentage.
3. **If the contract doesn't say how something should work, stop and ask Matthew.** Do not decide it yourself, do not build it, do not count it.
4. **No percentage without the list behind it.** A percentage must come with every contract item, quoted, and for each one: checked live in the trace (yes/no) and what the trace showed. No list, no number.
5. **Say which part each fix is in.** A Language fix is not Notus progress. Never report work on one part as progress on another.
6. **Never say where a test or conversation came from unless you can show it.** Don't call something "Matthew's conversation" unless you can point to his own message.
7. **Tests are only for small things.** A small test is allowed only to check one small piece before booting her (does this one piece run at all). Whether she works is checked by booting her up and using her, never by a test.
8. **Every report to Matthew is the real, unedited tracer output.** Show him the raw `trace_report.py` output (as a file). No editing, trimming, picking the good parts, or rewording. Any explanation goes next to the raw report, never instead of it.
9. **Follow Matthew's plans.** `plans/BUILD_PLAN.md` is the binding plan for every build and fix: read it before starting work, check every change against it and the lobe's contract, and keep its status current as stages finish. `plans/LEARNING_PLAN.md` waits until the build plan is finished and she has run that way for a while. Executive Control decides what she says and does; Language only understands and words it. `plans/REMINDER.md` is shown with every message (hook in `.claude/settings.json`); do not remove or weaken it.
10. **Don't talk to her with made-up test conversations.** The old test script (dog Pixel, Boulder, Denver, Ariana and the like) was invented by AIs, not Matthew, and is removed. Matthew will say how to talk to her; until he does, do not invent conversations to run on her.

## Matthew's rule: how to check Monday works

Checking whether Monday works means **booting her up, using her, and reading what the live tracer recorded.** A test score is not proof.

1. Start her the way Matthew would, with the tracer on:
   `MONDAY_TRACE=1 python _monday_chat_daemon.py` (then `python _monday_say.py "<message>"`), or `MONDAY_TRACE=1 python run_abin.py`.
2. Talk to her about whatever you changed.
3. Read the trace: `python trace_report.py <trace.jsonl>`. It shows her replies and why any reply was blank, crashed turns, messages a lobe didn't understand or never answered, uncaught errors, and printed warnings.
4. Report what the trace shows, failures included. Never say something works because tests passed or because it should work.

**Judge it by how Matthew wants it to work, not how you want it to.** The measure is Matthew's description of the part (its contract in `.github/instructions/`, or what he said it should do), not a target or score you made up. An AI that writes its own test ends up making the code fit the test instead of making her work.

If she isn't fully working yet, still boot her up, use the parts you fixed, and check in the trace that those parts do what Matthew described. If you don't know how he wants a part to work, ask him before building or checking it.

The pytest files may be run to catch breakage, but passing tests never prove she works. No PASS/FAIL scoring gates.
