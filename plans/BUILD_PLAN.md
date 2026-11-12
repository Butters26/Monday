# Monday Whole-Brain Build Plan (Matthew's plan, Nov 12, 2026)

**This plan is binding. Every build or fix must follow it. Check every change against it before making it.**
Live copy: "Monday Build Plan" doc (https://claude.ai/artifact/3sJaBEDJ5LSLeQkoBdCTes). If the doc and this file differ, read the doc and update this file.
Learning has its own plan: `plans/LEARNING_PLAN.md` (it waits until this plan is finished).

**Status:** Nov 12: plan approved and saved. Executive Control conductor design decided and built (section below); boot check clean; live check with conversation waiting on Matthew.

The goal: every lobe does the job in its contract (`.github/instructions/`) and works with the others as one team, with no script running the turn.

## How "done" is judged

- **Done for a lobe** = every item in its contract seen working live in the tracer, with the raw report given to Matthew. Nothing else counts.
- **Done for the brain** = a long live conversation where every lobe does its job, every announcement has a lobe that uses it, and the old turn script is gone.
- Where code, notes or this plan disagree with a lobe's contract, the contract wins, and the conflict is reported to Matthew.
- Facts about "today" come from the Nov 12 live run (its report was removed: it replayed an old AI test script).

## Part 1: Each lobe's fixes

| Lobe | Its job (contract) | Wrong today (Nov 12) | Fix |
| --- | --- | --- | --- |
| Thalamus | Only carries messages; decides nothing | Runs the whole turn as a script | Script removed piece by piece (Part 3) |
| Perception | Recognize what comes in, keep which sense | Typed words only; mic and camera saved for last (Matthew) | Typed words rechecked; mic and camera last |
| Sensory Integration | Combine recognitions into one moment | Builds the moment; only Notus hears it | Moment reaches every lobe that needs it (Part 2) |
| Language | Understand words; put given meaning into words; invents nothing | Decides what kind of reply to give and tries up to 10 (Claude built this); misreads names, "used to", "really" and more | Reply-deciding moved out to Executive Control; Language only understands and expresses; misreadings fixed against its contract |
| Reasoning | Conclusions and explanations, keeping uncertainty | Grades Language's sentences; its "understood" goes to nobody | Its conclusions go to Executive Control, Emotion, Metacognition and Notus |
| Notus (memory) | Keep experienced / told / concluded apart; give back what's asked | Does this, files facts itself (fine, Matthew); "contradicts" goes to nobody; earlier bugs overwrote facts | Contradictions go to Reasoning; every contract item checked live with memory wiped first |
| Executive Control | Goals, choosing actions, holding back impulses | Sets a goal each turn; only Motor reads it | Becomes the decider: what she says, asks, does or holds back |
| Conversation | Tracks the exchange and what needs answering | Reads each turn, tells nobody | Tells Executive Control what the turn needs answered |
| Social Context | Tone, relationship, expectations; cues kept apart from guesses | Heard by Emotion, Reasoning, Language; misread "I hate mornings" as a greeting (fixed Nov 12) | Also reaches Executive Control |
| Attention | Picks focus, turns down the rest | Ranks signals; handed to Reasoning by the script | Announces focus; Executive Control can steer it |
| Novelty | Flags what's new or unexpected | Score reaches nobody that decides anything | Goes to Attention and Reasoning |
| Pattern Recognition | Finds repeats and trends, never calls them causes | Produced "to then bed then early keeps happening" | Patterns from real observations, sent to Reasoning to judge |
| Shared Representation | Keeps a meaning the same between lobes | Untraced (172 messages handled) | Checked that meanings survive lobe to lobe |
| Metacognition | Checks the quality of her thinking, signals problems | Checks every turn and can rewrite her sentence, which isn't its job | Checks Reasoning's conclusions and signals back; no rewriting |
| Meta-awareness | Keeps track of what she's doing inside | Told about each turn, keeps nothing others use | Hears every announcement; answers when asked what she's doing |
| Values | What matters to her, changed by experience (README; no contract file) | Only answers when asked | Executive Control and Emotion ask it; Matthew writes the contract |
| Motor Action | Carries out a chosen action, reports what really happened | Plans every turn though no action exists | Acts only when Executive Control picks an action |
| Output | Delivers, never claims a failed delivery worked | Delivers every turn | Checked: delivered vs failed reported truthfully |
| Voice | Gives prepared words their sound | Speaks every reply | Checked against its contract |
| Autonomous Thinking | Starts and keeps up her own thoughts | Sends 111 messages; where they go is untraced; needs overhaul (Matthew, Nov 3) | Overhaul: thoughts go to Reasoning and Notus, results to Executive Control |
| Autonomous Speech | Decides when she speaks unprompted | Not built | Built; proposes to Executive Control, which decides |
| Emotion | Her feelings from her own state, not word ratings (Matthew, Nov 3) | Running; parked | Last (Matthew, Nov 3) |

Still to build: the missing social-brain parts, experience, reflection, reinforcement. Each gets a contract from Matthew first.

## Part 2: The team

No script and no boss lobe giving orders: each lobe listens for what it needs and announces what it finds, through Thalamus. One lobe makes each kind of decision, from its contract.

**Who decides what**

| Decision | Lobe |
| --- | --- |
| What she does, says, asks, or holds back | Executive Control |
| What the words mean; how to word what she means | Language |
| What follows, what's likely, what's still unknown | Reasoning |
| What she remembers and where it came from | Notus |
| What she focuses on | Attention |
| How she feels | Emotion |
| Whether her thinking holds up | Metacognition |
| When she has something to bring up on her own | Autonomous Speech proposes, Executive Control decides |

**Who tells whom**

| Lobe | Announces | Heard by |
| --- | --- | --- |
| Perception | what it recognized | Sensory Integration |
| Sensory Integration | the moment | Notus, Language, Novelty, Attention, Meta-awareness |
| Language | what was meant (who, what, asked or told) | Conversation, Social Context, Reasoning, Notus, Pattern, Emotion |
| Conversation | what this turn needs answered | Executive Control, Attention |
| Social Context | tone and relationship | Emotion, Reasoning, Executive Control |
| Novelty | what's new or unexpected | Attention, Reasoning |
| Pattern Recognition | repeats and trends | Reasoning |
| Notus | what this brings to mind; contradictions | Reasoning, Emotion |
| Attention | what matters most now | Reasoning, Executive Control |
| Reasoning | conclusions, sure or unsure | Executive Control, Emotion, Metacognition, Notus |
| Metacognition | problems in the thinking | Reasoning, Executive Control |
| Emotion | how she feels | Executive Control, Attention, Notus, Output, Voice |
| Executive Control | what she'll do: the meaning to say, or an action | Language, Motor Action, Attention |
| Language | the sentence | Output |
| Output | delivered or failed | Voice, Conversation, Notus |
| Autonomous Thinking | a thought to work on | Reasoning, Notus |
| Autonomous Speech | something worth bringing up | Executive Control |

Meta-awareness hears every announcement. Any lobe can ask Notus to recall something or Values what matters. Shared Representation keeps meanings the same along the way.

**A turn, as a team:** he speaks → the moment reaches every lobe that needs it → each does its job at once (meaning, memory, tone, focus, conclusions, feeling) → Executive Control decides what she says → Language words it → Output and Voice deliver it → Notus keeps what she said.

## Executive Control: the conductor (decided Nov 12)

Executive Control runs her brain the way the prefrontal cortex does. It is not a goal list; it drives the other lobes. It runs as a loop, during conversation and while she's idle:

1. **Workspace (working memory):** every lobe's findings come together in one live picture of right now (what was said and meant, what she remembers, Reasoning's conclusions, how she feels, the social read, what's new, her focus). Items fade when they stop mattering.
2. **Decide:** from the workspace it chooses her current purpose (understand him, answer him, find out more, comfort, act, think something through), weighing Reasoning, Emotion, Values and Social Context.
3. **Plan:** breaks the purpose into steps, each given to the lobe whose job it is (Notus recall, Reasoning work out, Language say, Motor do).
4. **Direct:** sends those requests through Thalamus; results come back into the workspace.
5. **Hold back:** stops impulses that would derail the purpose; a strong enough impulse can still win (Matthew, Nov 3: Emotion can override Reasoning if another lobe sides with it).
6. **Monitor:** checks each step; a failed step (nothing remembered, Reasoning rejects it, he says it's wrong) changes the plan or the purpose.
7. **Switch:** new input or a bigger need interrupts the current purpose; the old one is set aside, not lost.

It never does another lobe's specialist work itself: it asks the lobe whose job it is.

**Built Nov 12** (`executive_control_lobe.py`; old version in `legacy/`). Its situation-to-purpose rules, ranks, steps and impulse threshold are in `executive_purposes.txt` in her runtime folder, placeholder lines for Matthew to change. It listens to Reasoning (`understood`), Social Context (`social_read`) and Notus (`remembered`); its decisions show in the trace report's EXECUTIVE CONTROL section.

**Still needed from other lobes:**
- Language: take a purpose from Executive Control and word it (until then every "say" step is recorded as waiting).
- Output and Motor Action: report when something was actually done, so Executive Control can see a step really happened.
- Conversation: announce the turn itself instead of the turn script handing it over.
- Autonomous Thinking: announce its thoughts so they reach the workspace.
- Live check with conversation: waiting on Matthew saying how to talk to her (law 10).

## Part 3: All 100% together

Built in the order a reply depends on, so she keeps talking the whole time. Each stage ends the same way: boot her with the tracer, talk to her, Matthew gets the raw report, and the finished lobes' pieces of the old script are cut out.

1. **The deciding spine:** Executive Control decides; Language only understands and words; Reasoning's conclusions reach Executive Control; Conversation says what needs answering. Language's reply-choosing goes to legacy/.
2. **Memory finished:** every Notus contract item checked live with memory wiped first; contradictions reach Reasoning.
3. **What comes in:** the moment reaches every lobe in Part 2; Social Context, Novelty, Attention and Pattern announce to their listeners.
4. **The checkers:** Metacognition checks thinking instead of rewriting sentences; Meta-awareness keeps track; Shared Representation checked.
5. **What goes out:** Motor Action, Output, Voice; Values gets its contract and is asked by Executive Control and Emotion.
6. **On her own:** Autonomous Thinking overhauled; Autonomous Speech built.
7. **The missing parts:** social-brain parts, experience, reflection, reinforcement, each after Matthew gives its contract.
8. **Emotion**, last.
9. **Script out:** the last of Thalamus's turn script removed; lobes run at the same time.

**Whole-brain proof:** a long live conversation with the tracer on: every lobe does its contract job, no announcement goes to nobody, no blank or failed reply passed off as silence, and the raw report goes to Matthew unedited.

**Sunday:** not promised. Stages 1 and 2 are the realistic target; each stage's raw report shows exactly how far she got.
