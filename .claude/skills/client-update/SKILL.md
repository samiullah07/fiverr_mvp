---
name: client-update
description: Use after finishing a phase, or when the user wants a Fiverr-ready progress update message for the client. Drafts a concise, honest update in the freelancer's voice, grounded in what actually got done, referencing the phase plan the client already agreed to.
disable-model-invocation: false
---

Draft a short message the user (the freelancer) can paste directly into
Fiverr chat with their client. Ground it in:

- `docs/PROJECT_PLAN.md` — which phase/milestone this corresponds to
- What actually happened this session (check `git log` since the last
  update if unsure, or ask the user what to include)
- The tone of the freelancer's prior messages in `docs/CLIENT_BRIEF.md`'s
  history — direct, friendly, no over-promising

Structure:

1. One line: what phase/milestone just wrapped, in plain terms (e.g. "Phase
   1 is done — live transcription is working").
2. 2–4 bullets of concrete, demoable progress (not implementation jargon —
   things the client can picture: "you'll see live text appear as you
   speak in a Teams call").
3. If anything is behind, say so plainly and give a real reason + revised
   expectation — don't bury it.
4. One line on what's next, matching `docs/PROJECT_PLAN.md`.

Do not overstate completeness — if `qa-latency-tester` hasn't verified
something yet, don't claim it works across all three meeting platforms.
Offer to include a short screen-recording note (client can't see terminal
output, so a quick clip or screenshot is worth suggesting).
