# How to use this scaffold

This is not the app — it's the Claude Code project setup that will help you
*build* the app with discipline, on a fixed-price, fixed-scope Fiverr job.
No feature code is included on purpose; you said you're using Claude Code
for the actual coding.

## What's in here

```
meeting-copilot/
├── CLAUDE.md                  <- always-loaded project memory & scope rules
├── docs/
│   ├── CLIENT_BRIEF.md        <- the contract, extracted from your buyer chat
│   ├── PROJECT_PLAN.md        <- the 3 phases, mapped to a Claude Code workflow
│   └── ARCHITECTURE.md        <- tech stack + the key decisions already made
├── .claude/
│   ├── settings.json          <- wires up the hooks below
│   ├── agents/                <- 8 subagents, one per specialty
│   ├── skills/                <- /plan-phase, /scope-check, /client-update, /latency-report
│   ├── commands/               <- /deliver-phase, /test-e2e (quick shortcuts)
│   └── hooks/                 <- scope_guard.py, format_after_edit.py, session_context.py
└── .mcp.json                  <- two optional MCP servers, disabled by default use
```

## First run

1. Copy this whole `meeting-copilot/` folder to wherever you want the repo.
2. `cd meeting-copilot && git init`
3. Open it with Claude Code (`claude` in the terminal, in this directory).
4. On session start you'll see a short status banner (that's the
   `SessionStart` hook working). Claude will also have read `CLAUDE.md`
   automatically.
5. Read through `docs/CLIENT_BRIEF.md` yourself once, too — it's written
   for Claude, but it's also the cleanest single summary of what you
   actually agreed to deliver. Worth having memorized before you start
   billing hours against it.

## Day-to-day workflow

For each phase (1, 2, 3 from `docs/PROJECT_PLAN.md`):

1. `/plan-phase 1` (or 2, or 3) — this puts Claude into plan mode and
   produces a concrete plan grounded in the brief, **before any code is
   written**. Review it. On a fixed-price job, this step is what keeps you
   from burning unpaid hours on a wrong turn.
2. Approve the plan (or send it back with corrections).
3. Let Claude execute, delegating to the relevant subagent
   (`audio-capture-engineer`, `transcription-engineer`,
   `rag-pipeline-engineer`, `llm-integration-engineer`,
   `overlay-ui-engineer`) — it's told to do this automatically via
   `CLAUDE.md`, but you can also say e.g. "have the
   rag-pipeline-engineer subagent handle this" explicitly.
4. Before calling the phase done: `/deliver-phase <N>` — runs
   `/scope-check` (via the `scope-guard` subagent) and a `security-reviewer`
   pass, and a latency check if it's Phase 3.
5. `/client-update` — drafts the Fiverr message to your buyer. Read it
   before sending; it's a draft, not an autopilot.

## Two safety nets running automatically in the background

- **`scope_guard.py`** (PreToolUse hook): hard-blocks a small set of
  unambiguous scope violations as code is written — macOS/Linux audio APIs,
  cloud vector DBs, telemetry SDKs. It's deliberately narrow so it doesn't
  cry wolf on legitimate work; the real judgment call is the `scope-guard`
  *subagent* via `/scope-check`, which reads the whole diff with actual
  reasoning.
- **`format_after_edit.py`** (PostToolUse hook): runs `black`/`ruff` or
  `prettier` after edits, if you have them installed. Non-blocking.

## About the two optional MCP servers in `.mcp.json`

Both are commented as optional — `sequential-thinking` (extra structured
reasoning for the trickiest logic: question-detection + retrieval +
latency budgeting) and `memory` (persistent notes across many sessions over
your 14–21 day build). Neither is required; `CLAUDE.md` + `docs/` already
carry most of what a fresh session needs. Delete the file or the entries
you don't want.

## One more thing

`docs/CLIENT_BRIEF.md` §9 has a short, non-blocking note about
recording-consent laws, since this app captures other meeting participants'
audio too. Worth a one-line mention in your setup instructions to the
client — cheap to add, and it's the kind of thing that's better flagged
proactively than not.

Good luck with the build — this is a genuinely interesting project to have
landed as a first Fiverr order.
