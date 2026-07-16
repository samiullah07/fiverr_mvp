"""
Meeting Copilot — Phase 3 Backend Orchestration

This service wires together the Phase 1 (audio + transcription) and Phase 2 (RAG + LLM)
components into a single FastAPI process that exposes a WebSocket endpoint at
ws://127.0.0.1:8765/overlay for the Electron overlay.

Architecture:
┌─────────────┐    AudioManager (daemon threads)    ┌──────────────────┐
│ Microphone  │ ───► VAD + resample ────────────────►│ WhisperTranscriber │
└─────────────┘                                    └────────┬─────────┘
                                                             │ on_transcript callback (sync)
                                                             ▼
                    ┌─────────────────────────────────────────────────────┐
                    │  Rolling transcript buffer + question detection      │
                    │  When question detected:                            │
                    │    1. Retrieve relevant chunks (Retriever)          │
                    │    2. Build grounded prompt                         │
                    │    3. LLMClient.stream_answer_callback()           │
                    │       - each token → suggestion-token WS message   │
                    │       - final answer → suggestion-done WS message  │
                    └─────────────────────────────────────────────────────┘
"""
import asyncio
import json
import os
import re
import threading
from collections import deque
from contextlib import asynccontextmanager
from dataclasses import dataclass
from typing import Any, Callable, Dict, List, Optional, Tuple

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.websockets import WebSocketState
import uvicorn

# ============================================================================
# Import existing components (Phase 1 + Phase 2)
# ============================================================================
from backend.audio.capture import AudioManager
from backend.audio.transcription import WhisperTranscriber
from backend.rag.retrieval import Retriever, RetrievalResult
from backend.rag.llm import LLMClient, SYSTEM_INSTRUCTIONS, GROUNDING_TEMPLATE

# ============================================================================
# Thread-safe message queue (sync → async bridge)
# ============================================================================
class ThreadSafeQueue:
    """Lock-free queue for sync callbacks to push messages into async loop."""
    def __init__(self):
        self._queue: deque = deque()
        self._lock: asyncio.Lock = None  # Will be set in async context

    def push(self, msg: Dict[str, Any]) -> None:
        self._queue.append(msg)

    async def drain(self) -> List[Dict[str, Any]]:
        """Atomically drain the queue and return all pending messages."""
        if self._lock is None:
            self._lock = asyncio.Lock()
        async with self._lock:
            msgs = list(self._queue)
            self._queue.clear()
            return msgs


message_queue = ThreadSafeQueue()


def enqueue_message(msg: Dict[str, Any]) -> None:
    """Synchronous callers use this to push messages into the async loop."""
    message_queue.push(msg)


# ============================================================================
# WebSocket connection manager
# ============================================================================
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: Dict[str, Any]):
        """Send a message to all connected clients, removing dead ones."""
        data = json.dumps(message)
        dead = []
        for ws in self.active_connections:
            try:
                if ws.client_state == WebSocketState.CONNECTED:
                    await ws.send_text(data)
            except Exception:
                dead.append(ws)
        # Remove dead connections
        for d in dead:
            self.disconnect(d)
        return data

    async def send(self, websocket: WebSocket, message: Dict[str, Any]):
        await websocket.send_text(json.dumps(message))


manager = ConnectionManager()


# ============================================================================
# Question detection (Rule-based v1 — swappable module per CLIENT_BRIEF)
# ============================================================================
class QuestionDetector:
    """
    Detects presenter-directed questions in a rolling transcript.

    Rules (bias toward misses over false triggers):
    - Ends with ?  OR
    - Starts with interrogative (who/what/when/where/why/how/could/would/can)
    - Contains "walk me through" / "explain" / "how does" / "what is"
    - Addressed to presenter: "you mentioned", "your slide", "in your talk"

    Returns True if the most recent utterance looks like a question.
    """
    INTERROGATIVE_PATTERNS = [
        r'\b(who|what|when|where|why|how|which|whose|whom)\b',
        r'\b(could|would|can|will|should|might)\b.*\b(you|your)\b',
        r'\b(walk me through|explain|tell me about|describe)\b',
        r'\bhow does\b', r'\bwhat is\b', r'\bwhat are\b',
        r'\byou (mentioned|said|showed)\b',
        r'\byour (slide|demo|presentation|point)\b',
    ]

    def __init__(self, min_utterance_chars: int = 20):
        self.min_utterance_chars = min_utterance_chars
        self.compiled = [re.compile(p, re.IGNORECASE) for p in self.INTERROGATIVE_PATTERNS]

    def is_question(self, text: str) -> bool:
        text = text.strip()
        if len(text) < self.min_utterance_chars:
            return False

        # Check if ends with question mark
        if text.endswith('?'):
            return True

        # Check interrogative patterns
        for pattern in self.compiled:
            if pattern.search(text):
                return True

        return False

    def extract_recent_question(self, buffer: str) -> Optional[str]:
        """Extract the most recent question-like utterance from buffer."""
        # Split on sentence boundaries, look at last 2-3 sentences
        sentences = re.split(r'[.!?]+\s+', buffer)
        for sent in reversed(sentences[-3:]):
            if self.is_question(sent):
                return sent.strip()
        return None


# ============================================================================
# Rolling transcript buffer
# ============================================================================
class TranscriptBuffer:
    """
    Maintains a rolling window of transcribed text with timestamps.
    Used for question detection context and RAG queries.
    """
    def __init__(self, max_chars: int = 4000):
        self.max_chars = max_chars
        self._buffer: deque[Tuple[float, str]] = deque()  # (timestamp, text)

    def append(self, text: str, timestamp: float) -> None:
        self._buffer.append((timestamp, text))
        self._trim()

    def _trim(self) -> None:
        total = sum(len(t) for _, t in self._buffer)
        while total > self.max_chars and self._buffer:
            _, removed = self._buffer.popleft()
            total -= len(removed)

    def get_text(self) -> str:
        """Return concatenated transcript text (oldest first)."""
        return ' '.join(t for _, t in self._buffer)

    def get_recent(self, max_chars: int = 1500) -> str:
        """Return most recent text up to max_chars."""
        text = ''
        for _, t in reversed(self._buffer):
            text = t + ' ' + text
            if len(text) >= max_chars:
                return text.strip()
        return text.strip()


# ============================================================================
# Orchestration state (global, accessed from lifespan + callbacks)
# ============================================================================
@dataclass
class OrchestrationState:
    audio_manager: Optional[AudioManager] = None
    transcriber: Optional[WhisperTranscriber] = None
    retriever: Optional[Retriever] = None
    llm_client: Optional[LLMClient] = None
    question_detector: Optional[QuestionDetector] = None
    transcript_buffer: Optional[TranscriptBuffer] = None
    executor: Optional[Any] = None  # ThreadPoolExecutor for RAG+LLM
    running: bool = False


orch_state = OrchestrationState()


# ============================================================================
# Callback handlers (called from sync threads — must be non-blocking)
# ============================================================================
def on_transcript(text: str, latency: float):
    """
    Called by WhisperTranscriber for each transcribed chunk.
    Runs in transcriber's background thread — must be fast.
    """
    import time
    timestamp = time.time()

    # 1. Add to rolling buffer
    if orch_state.transcript_buffer:
        orch_state.transcript_buffer.append(text, timestamp)

    # 2. Push transcript to overlay immediately
    enqueue_message({"type": "transcript-update", "text": text, "timestamp": timestamp})

    # 3. Check for question (non-blocking, just pattern match)
    question = None
    if orch_state.question_detector and orch_state.transcript_buffer:
        recent = orch_state.transcript_buffer.get_recent(1500)
        question = orch_state.question_detector.extract_recent_question(recent)
        if question:
            # Submit RAG+LLM to thread pool (non-blocking)
            if orch_state.executor:
                orch_state.executor.submit(
                    process_question_async, question
                )

    print(f"[BENCH] latency={latency:.2f}s detected={bool(question)} text={text!r}", flush=True)


def process_question_async(question: str):
    """
    Runs in thread pool: retrieve → build prompt → stream LLM.
    """
    import time
    start = time.time()

    if not orch_state.retriever or not orch_state.llm_client:
        return

    # 1. Retrieve relevant chunks
    retrieve_start = time.time()
    try:
        results = orch_state.retriever.retrieve(question, n_results=5)
    except Exception as e:
        retrieve_time = time.time() - retrieve_start
        print(f"[BENCH] question_e2e=error | retrieve={retrieve_time:.2f}s | error=retrieval", flush=True)
        enqueue_message({"type": "error", "message": f"Retrieval failed: {e}"})
        return
    retrieve_time = time.time() - retrieve_start

    if not results:
        print(f"[BENCH] question_e2e=error | retrieve={retrieve_time:.2f}s | suggestion_produced=False | n_results=0", flush=True)
        enqueue_message({"type": "no-relevant-documents", "query": question})
        return

    # 2. Build grounded prompt
    context_lines = []
    citations = []
    for i, r in enumerate(results, 1):
        src = r.source_metadata
        fn = src.get("filename", "?")
        sec = src.get("section") or ""
        pg = src.get("page")
        page_str = f" p.{pg}" if pg else ""
        section_str = f" §{sec}" if sec else ""
        header = f"[{i}] {fn}{section_str}{page_str}"
        context_lines.append(f"{header}\n{r.text}\n")
        citations.append({
            "index": i,
            "filename": fn,
            "section": sec,
            "page": pg,
            "chunk_index": src.get("chunk_index"),
            "text": r.text[:200]  # truncated for citation display
        })

    context = "\n".join(context_lines)
    prompt = GROUNDING_TEMPLATE.format(context=context, question=question)

    # 3. Stream LLM answer with callback for each token
    full_answer = []
    llm_first_token_time = None

    def on_token(token: str):
        nonlocal llm_first_token_time
        full_answer.append(token)
        enqueue_message({"type": "suggestion-token", "fragment": token})
        if llm_first_token_time is None:
            llm_first_token_time = time.time() - start

    try:
        answer = orch_state.llm_client.stream_answer_callback(prompt, on_token)
    except Exception as e:
        enqueue_message({"type": "error", "message": f"LLM streaming failed: {e}"})
        print(f"[BENCH] question_e2e=error | suggestion_produced=False | error=llm", flush=True)
        return

    # 4. Send final answer with citations
    enqueue_message({
        "type": "suggestion-done",
        "text": answer,
        "citations": citations
    })

    elapsed = time.time() - start
    total_llm_time = time.time() - (start + retrieve_time)
    print(f"[BENCH] question_e2e={elapsed:.2f}s | retrieve={retrieve_time:.2f}s | llm_first_token={llm_first_token_time:.2f}s | llm_total={total_llm_time:.2f}s | n_results={len(results)} | suggestion_produced=True", flush=True)


# ============================================================================
# FastAPI app and WebSocket endpoint
# ============================================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan: start audio pipeline, background queue drain."""
    import concurrent.futures

    # 1. Initialize components
    orch_state.retriever = Retriever()
    orch_state.llm_client = LLMClient(provider=os.getenv("LLM_PROVIDER", "claude"))
    orch_state.question_detector = QuestionDetector()
    orch_state.transcript_buffer = TranscriptBuffer()
    orch_state.executor = concurrent.futures.ThreadPoolExecutor(max_workers=2)

    # 2. Initialize audio pipeline
    # AudioManager with transcription disabled (we handle it ourselves)
    orch_state.audio_manager = AudioManager(
        mic_aggressiveness=2,
        loopback_aggressiveness=2,
        enable_transcription=False
    )

    # 3. Initialize transcriber with our callback
    # "base.en" model for better accuracy than tiny.en (slower but more reliable)
    orch_state.transcriber = WhisperTranscriber(
        model_size="base.en",
        device="cpu",
        compute_type="int8",
        on_transcript=on_transcript
    )

    # 4. Start transcriber
    orch_state.transcriber.start()

    # 5. Start audio capture directly in its own dedicated daemon thread.
    #    AudioManager launches its own daemon capture threads internally and
    #    start_capture() returns immediately, so we do NOT route it through the
    #    shared ThreadPoolExecutor — that executor is reserved exclusively for
    #    RAG+LLM work (process_question_async). Routing a long-lived capture
    #    call through the 2-worker executor would starve question processing and
    #    deadlock on overlapping questions.
    def run_audio():
        def feed(audio_bytes):
            print(f"[DEBUG] on_speech fired: {len(audio_bytes)} bytes", flush=True)
            orch_state.transcriber.feed_audio(audio_bytes)
        try:
            orch_state.audio_manager.start_capture(on_speech=feed)
        except Exception as e:
            print(f"[orchestration] Audio capture error: {e}")
            enqueue_message({"type": "error", "message": f"Audio capture failed: {e}"})

    orch_state.running = True
    capture_thread = threading.Thread(target=run_audio, daemon=True)
    capture_thread.start()

    # 6. Background task: drain sync message queue → broadcast to WS clients
    async def queue_drain_task():
        while orch_state.running:
            try:
                msgs = await message_queue.drain()
                if msgs:
                    print(f"[DEBUG] draining {len(msgs)} messages", flush=True)
                for msg in msgs:
                    await manager.broadcast(msg)
                await asyncio.sleep(0.05)  # 20 Hz
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[orchestration] Queue drain error: {e}")
                await asyncio.sleep(0.1)

    drain_task = asyncio.create_task(queue_drain_task())

    yield

    # 7. Cleanup on shutdown
    orch_state.running = False
    drain_task.cancel()

    if orch_state.transcriber:
        orch_state.transcriber.stop()
    if orch_state.audio_manager:
        orch_state.audio_manager.stop()
    if orch_state.executor:
        orch_state.executor.shutdown(wait=True)


app = FastAPI(lifespan=lifespan)


@app.websocket("/ws/overlay")
async def overlay_websocket(websocket: WebSocket):
    """
    Main channel to the Electron overlay.
    Receives: {"type": "user-input", "action": "..."}, {"type": "assist-request"}
    Sends: transcript-update, suggestion-token, suggestion-done, no-relevant-documents, error
    """
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            payload = json.loads(data)
            action = payload.get("type")
            if action == "ping":
                await manager.send(websocket, {"type": "pong"})
            elif action == "user-input":
                cmd = payload.get("action")
                if cmd == "close":
                    await websocket.close()
            elif action == "assist-request":
                # Manual trigger: grab recent transcript and run RAG+LLM
                if orch_state.transcript_buffer and orch_state.executor:
                    recent = orch_state.transcript_buffer.get_recent(1500)
                    if recent and recent.strip():
                        orch_state.executor.submit(process_question_async, recent)
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(websocket)


# ============================================================================
# Utility functions for sync callbacks
# ============================================================================
def emit_transcript(text: str):
    enqueue_message({"type": "transcript-update", "text": text})


def emit_suggestion_token(fragment: str):
    enqueue_message({"type": "suggestion-token", "fragment": fragment})


def emit_suggestion_done(text: str, citations: Optional[List[Dict]] = None):
    enqueue_message({
        "type": "suggestion-done",
        "text": text,
        "citations": citations or []
    })


def emit_no_relevant_documents(query: str):
    enqueue_message({"type": "no-relevant-documents", "query": query})


def emit_error(message: str):
    enqueue_message({"type": "error", "message": message})


# ============================================================================
# Entry point
# ============================================================================
if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8765)