"""
Real-time transcription using faster-whisper.

Buffers audio chunks (2.5s target with 0.5s overlap) and transcribes
them as they accumulate. Designed to be wired into AudioManager's on_speech callback.
"""

import threading
from collections import deque
from typing import Callable, Optional
import time

import numpy as np
from faster_whisper import WhisperModel


class TranscriptionBuffer:
    """
    Thread-safe audio buffer for chunking speech before transcription.

    Uses time-based windows with overlap:
    - target_chunk_seconds: 1.5s target before transcription (latency-optimized)
    - overlap_seconds: 0.3s carried over to next chunk

    This approach prioritizes latency (meeting the 1-3s target from question
    to suggestion) while maintaining reasonable transcription accuracy.
    The 1-3s target starts when the question is spoken, so we need to
    minimize buffer time before transcription begins.

    Note: 1.5s buffer + ~0.5-0.8s faster-whisper transcription = ~2-2.5s total
    before LLM prompt construction.
    """

    def __init__(
        self,
        sample_rate: int = 16000,
        target_chunk_seconds: float = 1.5,
        overlap_seconds: float = 0.3,
    ):
        self.sample_rate = sample_rate
        self.target_chunk_bytes = int(sample_rate * 2 * target_chunk_seconds)  # 16-bit mono
        self.overlap_bytes = int(sample_rate * 2 * overlap_seconds)

        self._queue: deque[bytes] = deque()
        self._accumulated_bytes: int = 0
        self._overlap_buffer: bytes = b""
        self._lock = threading.Lock()

    def append(self, audio_bytes: bytes) -> int:
        """
        Append speech audio bytes to the buffer.

        Returns:
            Current total accumulated bytes (including overlap)
        """
        with self._lock:
            self._queue.append(audio_bytes)
            self._accumulated_bytes += len(audio_bytes)
            return self._accumulated_bytes + len(self._overlap_buffer)

    def ready_for_transcription(self) -> bool:
        """Check if buffer has enough audio for a transcription chunk."""
        with self._lock:
            return (self._accumulated_bytes + len(self._overlap_buffer)) >= self.target_chunk_bytes

    def get_chunk(self) -> Optional[bytes]:
        """
        Extract a transcription chunk with overlap from previous chunk.

        Returns:
            Audio bytes ready for transcription, or None if not enough data
        """
        with self._lock:
            total_available = self._accumulated_bytes + len(self._overlap_buffer)
            if total_available < self.target_chunk_bytes:
                return None

            # Combine overlap from previous + new audio
            combined = self._overlap_buffer + b"".join(self._queue)

            # Take target chunk size
            chunk = combined[:self.target_chunk_bytes]

            # Keep remainder (including any leftover from overlap)
            remainder = combined[self.target_chunk_bytes:]

            # Store last overlap_bytes of remainder as new overlap
            if len(remainder) > self.overlap_bytes:
                self._overlap_buffer = remainder[-self.overlap_bytes:]
                remainder = remainder[:-self.overlap_bytes]
            else:
                self._overlap_buffer = remainder
                remainder = b""

            # Clear queue and update byte count
            self._queue.clear()
            self._accumulated_bytes = len(remainder)

            return chunk

    def get_pending_bytes(self) -> int:
        """Return total pending bytes (for debugging)."""
        with self._lock:
            return self._accumulated_bytes + len(self._overlap_buffer)


class WhisperTranscriber:
    """
    faster-whisper based real-time transcriber.

    Runs transcription in a background thread to avoid blocking audio capture.
    """

    def __init__(
        self,
        model_size: str = "tiny.en",
        device: str = "cpu",
        compute_type: str = "int8",
        on_transcript: Optional[Callable[[str, float], None]] = None,
    ):
        """
        Initialize the transcriber.

        Args:
            model_size: Whisper model size (tiny, base, small, medium, large_v2, large_v3)
            device: "cpu" or "cuda"
            compute_type: Model compute type (int8, float16, float32)
            on_transcript: Callback(spoken_text, latency_seconds) called on each transcription
        """
        self.model_size = model_size
        self.device = device
        self.compute_type = compute_type
        self.on_transcript = on_transcript

        # Load model
        print(f"Loading Whisper model '{model_size}' on {device}...")
        self.model = WhisperModel(
            model_size,
            device=device,
            compute_type=compute_type,
        )
        print("Whisper model loaded.")

        # Buffer and thread
        self.buffer = TranscriptionBuffer()
        self.start_time: Optional[float] = None  # Track when first audio arrived
        self._transcription_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def _transcribe_chunk(self, audio_bytes: bytes) -> str:
        """Transcribe a single audio chunk."""
        # Convert bytes to numpy array
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16).astype(np.float32) / 32768.0

        # Transcribe
        segments, _ = self.model.transcribe(audio_array, beam_size=1)
        return "".join(seg.text for seg in segments).strip()

    def _transcription_loop(self):
        """Background loop that transcribes buffered audio."""
        while not self._stop_event.is_set():
            if self.buffer.ready_for_transcription():
                chunk = self.buffer.get_chunk()
                if chunk:
                    start_time = time.time()
                    text = self._transcribe_chunk(chunk)
                    latency = time.time() - start_time

                    if text and self.on_transcript:
                        self.on_transcript(text, latency)
            else:
                # Small sleep to avoid busy-waiting
                time.sleep(0.05)

    def start(self):
        """Start the transcription background thread."""
        self._stop_event.clear()
        self._transcription_thread = threading.Thread(target=self._transcription_loop, daemon=True)
        self._transcription_thread.start()
        print("Transcription thread started.")

    def stop(self):
        """Stop the transcription thread."""
        self._stop_event.set()
        if self._transcription_thread:
            self._transcription_thread.join(timeout=2.0)
        print("Transcription thread stopped.")

    def feed_audio(self, audio_bytes: bytes):
        """
        Feed speech audio to the buffer.

        This is designed to be called from AudioManager's on_speech callback.
        """
        self.buffer.append(audio_bytes)


# Default transcriber instance for convenience
_default_transcriber: Optional[WhisperTranscriber] = None


def create_transcriber(
    model_size: str = "tiny.en",
    device: str = "cpu",
    compute_type: str = "int8",
    on_transcript: Optional[Callable[[str, float], None]] = None,
) -> WhisperTranscriber:
    """Factory function to create a WhisperTranscriber."""
    return WhisperTranscriber(
        model_size=model_size,
        device=device,
        compute_type=compute_type,
        on_transcript=on_transcript,
    )