---
name: latency-report
description: Use around Phase 3 and before final delivery to verify the 1-3 second question-to-suggestion latency target end-to-end. Delegates to qa-latency-tester and produces a stage-by-stage breakdown.
disable-model-invocation: false
---

Delegate to the `qa-latency-tester` subagent to produce a latency breakdown
of the full pipeline described in `docs/ARCHITECTURE.md` ("Data flow"
section):

```
audio chunking -> transcription -> question detection -> retrieval
-> LLM time-to-first-token -> overlay render
```

Ask for:

1. A measured (not estimated) time for each stage, from a real or realistic
   test run — not a theoretical best case.
2. Total end-to-end time compared against the client's 1–3s target
   (`docs/CLIENT_BRIEF.md` §5).
3. If the target is missed, which single stage is the biggest contributor,
   and 1–2 concrete suggestions to shave time off it (e.g. smaller
   transcription model, smaller top-k in retrieval, shorter system prompt,
   a faster embedding model) — grounded in what's actually slow, not
   generic advice.

Present the result as a simple table (stage, measured time, % of budget)
followed by the verdict and any recommended follow-up work.
