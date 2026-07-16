---
description: Run the full pre-delivery checklist for the current phase (scope check, security review, latency check if Phase 3+)
argument-hint: [1|2|3]
---

Run the following in order for phase $ARGUMENTS, stopping and reporting if
any step fails rather than continuing past it:

1. Run the `/scope-check` skill.
2. Delegate to `security-reviewer` for a review of everything touched this
   phase.
3. If phase is 3 (or this is final delivery), run `/latency-report` too.
4. Summarize: is this phase actually ready to call done and report to the
   client, or is there a blocking item first? Be direct about it.
