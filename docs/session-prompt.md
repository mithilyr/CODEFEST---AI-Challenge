# Session start prompt

`CLAUDE.md` at the repo root is loaded automatically every session, so the project
context, corpus findings and working rules are already in scope. This file holds the
short kickoff message to paste on top of it.

---

## Standard kickoff (paste this)

```
Working on the Ashen Era assistant (Codefest 1B). CLAUDE.md has the project context.

Before proposing anything:
1. Run `python -m pytest` and `python -m src.ingest.pipeline` to confirm the
   current state, and tell me if either disagrees with CLAUDE.md.
2. Check `git log --oneline | head -15` and `docs/decisions.md` for what was
   decided since you last saw this.

Then tell me, in a few lines: what state the repo is in, what the next piece of
work is per docs/roadmap, and anything in CLAUDE.md you think is now wrong.

How I want you to work:
- Measure before asserting. Three of our assumptions have already been overturned
  by a five-minute check. If a claim is going into a doc, the report or the video,
  verify it first and show me the evidence.
- Deterministic-first. Do not add an LLM call, dependency or framework without
  saying what it measurably improves over the simpler option.
- Challenge me. If my reasoning is weak or the approach is overengineered, say so
  plainly rather than agreeing.
- Commit atomically as you go, with messages that say why and cite the measurement.
- Never write an API key anywhere except .env.

Today I want to work on: <FILL THIS IN>
```

---

## Variants

**Picking up mid-task**

```
Continue the Ashen Era assistant (Codefest 1B). CLAUDE.md has the context.
Check git log and `git status` first, tell me exactly where the last session
stopped and what is half-finished, then propose the smallest next step.
Do not start work until I confirm.
```

**Debugging**

```
Ashen Era assistant (Codefest 1B), see CLAUDE.md.
Something is wrong: <SYMPTOM>.
Reproduce it first and show me the actual output before proposing a fix.
Do not fix anything you have not reproduced. If a test would have caught this,
write the test as part of the fix.
```

**Review / defensibility check**

Run this before the site visit — every member must be able to explain any part
on demand, and inability to do so is disqualifying.

```
Ashen Era assistant (Codefest 1B), see CLAUDE.md.
Review <FILE OR MODULE> as a judge would. For each part, ask: could a student who
did not write this explain why it exists and what breaks without it?
Flag anything that is unnecessarily clever, unexplained, or that we could not
defend. Suggest deletions, not additions.
```

**Writing the report or video script**

```
Ashen Era assistant (Codefest 1B), see CLAUDE.md.
Drafting <DELIVERABLE>. Every factual claim must be traceable to a measurement in
eval/results/, docs/decisions.md, or a command I can run right now. If a claim
cannot be backed, flag it instead of writing it. Note that our earlier claim about
the 1C baseline answering 360 AS was measured and found false - do not repeat it.
```

---

## Why the kickoff is shaped this way

- **Verify state first.** The repo changes between sessions and CLAUDE.md goes stale.
  Making that the first step catches drift before it becomes a wrong plan.
- **Ask what is now wrong.** An assistant that only confirms is not useful. This
  project has had three assumptions overturned; inviting correction is cheap.
- **State the working rules every time.** They do not survive a context reset, and
  they are what keeps the work defensible under judge questioning.
- **Name today's task explicitly.** A session without a stated goal drifts into
  plausible-looking work nobody asked for.
