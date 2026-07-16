---
name: plan-phase
description: Use when starting Phase 1, 2, or 3 of the meeting copilot build, or when re-planning after scope feedback. Produces a concrete implementation plan grounded in docs/CLIENT_BRIEF.md and docs/PROJECT_PLAN.md before any code is written. Invoke as /plan-phase <1|2|3>.
disable-model-invocation: false
---

The user invoked `/plan-phase $ARGUMENTS`. Treat `$0` (or the first token of
`$ARGUMENTS`) as the phase number (1, 2, or 3).

Do the following, and enter Claude Code's plan mode for this (don't write or
edit any files yet):

1. Re-read `docs/CLIENT_BRIEF.md` and the section of `docs/PROJECT_PLAN.md`
   for the requested phase.
2. Check current repo state (`git status`, relevant directory listing) to
   see what already exists vs. what's still to build for this phase.
3. Produce a concrete, ordered implementation plan for this phase only:
   - Which subagent(s) own which pieces (reference `.claude/agents/`).
   - Order of implementation (what has to exist before what).
   - Explicit exit criteria copied from `docs/PROJECT_PLAN.md` for this
     phase — don't paraphrase them into something looser.
   - Anything ambiguous in the brief that needs a decision before starting.
   - A rough sense of what's genuinely hard vs. straightforward, so time
     gets allocated sensibly on a fixed-price job.
4. Do **not** start writing code from inside this skill. Present the plan
   and wait for approval, exactly as Claude Code's plan mode is meant to
   work — this is a fixed-price, scope-locked project, and skipping the
   plan step is how budget gets blown.
