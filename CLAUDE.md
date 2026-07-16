# Meeting Copilot — Project Memory

Windows desktop app: live meeting transcription + local RAG over the user's
own documents + a floating overlay that suggests grounded answers to
follow-up questions in real time. Built for a fixed-price Fiverr client
(CAD $700, 14–21 days). Read `docs/CLIENT_BRIEF.md` before touching scope —
it is the contract, not a suggestion.

## Non-negotiable scope boundaries

Full detail in `docs/CLIENT_BRIEF.md`. Summary, because this is the thing
that will get violated first if it's not front and center:

- **Windows only.** No macOS/Linux code paths.
- **One LLM provider** (Claude or OpenAI, client's choice), not both at once.
- **Local-only.** No server you operate, no cloud vector DB, no telemetry.
- **RAG-primary answers.** Suggestions must come from the client's uploaded
  documents first; fall back to base LLM knowledge only when nothing
  relevant is found, and say so when that happens.
- **Continuous processing.** The live transcript is processed throughout the
  meeting, not just once on manual trigger.
- This is a **meeting copilot for the presenter's own material**, not an
  interview-cheating tool — keep it framed that way in code, docs, and UI
  copy.

If a task looks like it needs something outside this list, stop and ask
rather than building it — see `.claude/agents/scope-guard.md`.

## Repo layout

```
/backend    Python + FastAPI: audio capture, transcription, RAG, LLM calls
/overlay    Electron + React: floating always-on-top suggestion overlay
/docs       CLIENT_BRIEF.md, PROJECT_PLAN.md, ARCHITECTURE.md
```

(Both `/backend` and `/overlay` get created during Phase 0/1 — don't assume
they exist yet if the tree is empty.)

## How to work in this repo

1. Start any new phase of work with **`/plan-phase <1|2|3>`** and use Claude
   Code's plan mode (Shift+Tab) before writing code. Don't jump straight to
   implementation on a fixed-price, scope-locked project — the plan is what
   keeps hours on budget.
2. Delegate implementation to the specialist subagent for that layer
   (`audio-capture-engineer`, `transcription-engineer`, `rag-pipeline-
   engineer`, `llm-integration-engineer`, `overlay-ui-engineer`,
   `qa-latency-tester`) rather than doing everything in the main thread —
   see each agent file in `.claude/agents/` for what it owns.
3. Before marking a phase "done," run **`/scope-check`**.
4. After a phase is done, run **`/client-update`** to draft the Fiverr
   progress message.
5. Before/around Phase 3 delivery, run **`/latency-report`** to verify the
   1–3s target end-to-end, not just per-component.

## Coding conventions

- Python: type hints, `black` + `ruff` formatting (hooks will try to run
  these automatically after edits — see `.claude/settings.json`).
- Secrets: only ever in `.env` (gitignored). Never hardcode API keys, never
  log full API keys or full document contents to disk in plaintext logs.
- Keep the audio/transcription/RAG/LLM/overlay layers loosely coupled behind
  clear interfaces — this is a fixed-scope MVP now, but the client has
  already signaled interest in "advanced features later," so avoid
  hard-coupling that would make Phase 2 features expensive to add.
- No new third-party services or API integrations without updating
  `docs/CLIENT_BRIEF.md` first — if it's not there, the client didn't agree
  to pay for it.

## What NOT to do (see `docs/CLIENT_BRIEF.md` §4 for the full list)

Do not add: macOS/Linux support, simultaneous multi-LLM support, cloud
hosting/multi-user/subscription billing, telemetry/analytics, a mobile
companion app, or interview-assistance framing/features. Any of these
belongs in a change order and a new quote, not a helpful surprise.
