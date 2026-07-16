---
name: scope-check
description: Use before marking any phase, feature, or the whole project "done" or ready to deliver. Delegates to the scope-guard subagent to audit recent changes against docs/CLIENT_BRIEF.md and reports drift in either direction (scope creep or gaps against what was promised).
disable-model-invocation: false
---

Delegate to the `scope-guard` subagent (via the Agent tool) to audit the
current state of the repo (or the diff for the current session, if that's
the more relevant scope) against `docs/CLIENT_BRIEF.md`.

Ask it explicitly to report:

1. Anything in the diff that matches the "explicitly out of scope" list in
   `docs/CLIENT_BRIEF.md` §4.
2. Anything in the "locked scope" (§3) or "binding acceptance criteria"
   (§6) that should exist by now but doesn't.
3. Any new dependency or external service not mentioned in the brief.

Surface the subagent's verdict directly to the user — don't soften a
"scope creep found" or "gap found" verdict into something vaguer. If it
comes back clean, say so plainly and move on.
