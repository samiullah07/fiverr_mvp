# Project Plan — Claude Code Workflow Mapping

Maps the 3 phases promised to the client onto concrete Claude Code sessions:
plan mode → subagent delegation → hook-enforced checks → QA → client update.

Each phase should be run as: **`/plan-phase N`** (produces a plan, no code
written yet) → you approve/adjust the plan → Claude executes it, delegating
to the relevant subagent(s) → `/scope-check` before you call it done →
`/client-update` to draft the Fiverr message.

---

## Phase 0 — Setup (do this first, not billed as a "phase" to the client)

- [ ] `git init`, `.gitignore` (must exclude `.env`, `*.key`, `venv/`,
      `node_modules/`, any local vector DB files, any transcript logs)
- [ ] Repo skeleton: `/backend` (Python/FastAPI), `/overlay` (Electron/React),
      `/docs`
- [ ] `.env.example` with placeholders: `LLM_PROVIDER=claude|openai`,
      `ANTHROPIC_API_KEY=`, `OPENAI_API_KEY=`
- [ ] Confirm with client (if not already answered): Claude or OpenAI for v1?
- [ ] Decide transcription approach: **local `faster-whisper`**, not the
      paid Whisper API — the brief says "no subscriptions needed beyond your
      API key" (singular), which only makes sense if transcription runs
      locally and the only paid API call is to the chosen LLM. Confirm this
      reading with the client before Phase 1 if there's any doubt — it
      changes hardware requirements (a decent CPU or a small GPU helps).

## Phase 1 — Audio & Transcription (Days 1–4)

**Owner subagent:** `audio-capture-engineer`, then `transcription-engineer`

- [ ] Enumerate Windows audio devices; capture default mic input
- [ ] Capture system audio via WASAPI loopback (so Teams/Zoom/Meet audio is
      picked up without any plugin in the meeting app itself)
- [ ] Mix or dual-stream mic + system audio with speaker-side tagging if
      cheaply available (nice-to-have, not required)
- [ ] Voice-activity detection + chunking (~2–3s windows, streaming)
- [ ] Feed chunks into local `faster-whisper` for streaming transcription
- [ ] **Exit criteria:** live transcript text appears in a terminal/log
      window as you speak, latency of a few hundred ms to ~1s per chunk

**Definition of done:** you can join a real Teams/Zoom/Meet call, speak, and
have someone else in the call speak, and see both show up as live text.

## Phase 2 — RAG + LLM (Days 5–8)

**Owner subagent:** `rag-pipeline-engineer`, then `llm-integration-engineer`

- [ ] Document ingestion: PDF/text upload → parse → chunk (semantic or
      fixed-size w/ overlap)
- [ ] Local embedding model + **Chroma** persistent local vector store (no
      cloud vector DB — client explicitly wants local-only; persists at
      `%LOCALAPPDATA%/MeetingCopilot/chroma` on Windows)
- [ ] Question-detection pass on the live transcript stream (classify
      "is this a question aimed at the presenter" vs. general chatter)
- [ ] On detected question: retrieve top-k relevant chunks → build a grounded
      prompt → call the client's chosen LLM (Claude or OpenAI) with
      streaming
- [ ] Apply the configurable "custom instructions" file (see
      `CLIENT_BRIEF.md §7`) as a system-prompt layer
- [ ] Explicit "not found in your documents" fallback behavior per the
      client's requested config option
- [ ] **CLI Test Harness (explicit Phase 2 exit deliverable):** a minimal
      Python REPL (`python -m rag.cli <docs_folder>`) that loads/reindexes
      documents from a folder, accepts a typed question, shows retrieved
      chunks with source filenames/sections, and returns a grounded LLM answer
      with inline citations — this is the handoff artifact for client testing
      before Phase 3 overlay exists.
- [ ] **Exit criteria:** given an uploaded PDF and a spoken question related
      to it, the pipeline returns a grounded, cited-to-source suggestion

## Phase 3 — Overlay + Integration + Testing (Days 9–12)

**Owner subagent:** `overlay-ui-engineer`, then `qa-latency-tester`

- [ ] Electron transparent, always-on-top overlay window
- [ ] IPC/local socket connection from overlay → Python backend
- [ ] Display streaming suggestion text as it arrives; simple question/answer
      history in the overlay
- [ ] Local "transcription active" indicator (see legal note in
      `CLIENT_BRIEF.md §9`)
- [ ] Full manual test pass: Teams call, Zoom call, Google Meet call — join,
      speak, get asked a question, verify overlay response and latency
- [ ] Latency measurement end-to-end (question spoken → suggestion visible)
      against the 1–3s target — use `/latency-report`
- [ ] Fix anything broken from this pass

## Days 13–21 — Buffer + bug-fix round

- [ ] Package as a Windows installer
- [ ] Write the setup instructions doc for the client (README + short setup
      video script if useful)
- [ ] Deliver, then use the included bug-fix round for anything that doesn't
      match `CLIENT_BRIEF.md`

---

## Weekly milestone message to send the client

If 14 days turns out to be tight, the brief already promised weekly
milestones as a fallback. Use `/client-update` at the end of each phase to
draft that message — don't leave the client guessing.
