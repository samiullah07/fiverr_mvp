# Architecture Decisions

## Stack

| Layer | Choice | Why |
|---|---|---|
| Overlay UI | Electron + React, transparent always-on-top `BrowserWindow` | Cross-meeting-app overlay without plugins; client already anchored on this in negotiation |
| Backend | Python + FastAPI, running as a local process (localhost only) | Best ecosystem for audio, Whisper, embeddings, Chroma |
| Audio capture | Windows WASAPI loopback (system audio) + default input device (mic) | Only reliable no-plugin way to capture Teams/Zoom/Meet audio on Windows |
| Transcription | **Local `faster-whisper`** (not the paid Whisper API) | Client wants "no subscriptions beyond your API key" — singular. Only the LLM call should be a paid API. Confirm with client if unsure. |
| Embeddings + vector store | Local sentence-embedding model + **Chroma** (local index file, not a cloud service) | Client explicitly wants local-only, no cloud dependency after delivery; Chroma chosen for better incremental add/remove support and metadata handling. Persists at `%LOCALAPPDATA%\MeetingCopilot\chroma` on Windows. Each chunk tagged with `document_id` (content hash) and `source_metadata` (filename, section/page). Delete old chunks before reinserting changed documents. LLM answers include source document attribution. |
| LLM | **One** of Claude or OpenAI, client's choice at config time | Locked scope — see CLIENT_BRIEF.md §3 |
| IPC | Local WebSocket or named pipe between Electron overlay and Python backend | Simple, low-latency, no external network hop |

## Data flow (the 1–3s path)

```
mic + system audio
   -> VAD/chunking (~2-3s windows)
   -> faster-whisper streaming transcription
   -> rolling transcript buffer
   -> question-detection pass
        (if question detected)
   -> Chroma retrieval over client's uploaded docs (with document_id + source_metadata tags)
   -> grounded prompt build (retrieved chunks + custom instructions)
   -> LLM streaming call (Claude or OpenAI)
   -> partial tokens pushed to overlay via IPC
   -> Electron overlay renders suggestion live
```

Every hop in this chain is a latency budget line item. When something is
slow, profile which hop it is before optimizing blindly — see
`qa-latency-tester` subagent.

## Non-negotiables baked into the architecture (from CLIENT_BRIEF.md)

1. **No server the freelancer operates.** Everything above runs on the
   client's machine. The only outbound network calls after delivery are to
   the client's chosen LLM provider's API, using the client's own key.
2. **No telemetry.** Don't add crash reporting, analytics, or usage pings
   without asking — this was never agreed and the client is privacy-
   conscious (personal documents going into RAG).
3. **Windows only.** Don't add `sys.platform` branches for macOS/Linux;
   don't pull in cross-platform audio abstraction layers "just in case" —
   it adds complexity the client isn't paying for.
4. **One LLM provider active at a time**, chosen via a single config value,
   not a runtime switcher UI.
5. **Persistent knowledge base.** Chroma uses a stable, documented data
   directory (`%LOCALAPPDATA%\MeetingCopilot\chroma` on Windows, the
   equivalent of `~/.local/share/MeetingCopilot/chroma` elsewhere), never a
   temp path, so the index survives app restarts and reinstalls.
6. **No duplicate accumulation on document replacement.** Every chunk carries a
   `document_id` (content hash) as metadata at embed time. Reindexing a changed
   document deletes all chunks with that `document_id` from Chroma before the
   new embeddings are inserted. This is part of the ingestion logic from day
   one, not a retrofit.
7. **Source attribution on every answer.** Retrieved chunk metadata
   (`filename`, `section`/`page`) flows into the LLM prompt so it can cite
   sources, and is surfaced to the user in the Phase 3 overlay — the user sees
   which document(s)/section(s) each suggestion drew from, not just the LLM's
   word for it.

## Open decision to confirm with client before Phase 2

Whether "primarily from uploaded documents" should also support **no
documents uploaded yet** gracefully (fall back straight to LLM with a note),
since a brand-new user won't have docs uploaded on first run. Recommended:
yes, since the client's own config wishlist (§7) already asks for a
"not found in documents, fall back to LLM" behavior — this is just the
zero-document edge case of that same behavior.
