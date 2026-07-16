"""Voice Activity Detection using WebRTC VAD with medium aggressiveness.

Uses webrtcvad_wheels for prebuilt Windows wheels (no Visual C++ Build Tools required).
"""

import webrtcvad
from typing import List, Tuple

# Audio parameters required by WebRTC VAD
VAD_SAMPLE_RATE = 16000
VAD_FRAME_MS = 30  # 10, 20, or 30 ms
VAD_CHANNELS = 1


class VoiceActivityDetector:
    """
    WebRTC-based voice activity detector using prebuilt wheels.

    Uses medium aggressiveness (2) as specified by the client.
    Supports 2.5s chunks with 0.5s overlap for smooth transcription.

    Note: webrtcvad only accepts 16-bit PCM audio.
    """

    def __init__(self, aggressiveness: int = 2, sample_rate: int = VAD_SAMPLE_RATE):
        """
        Initialize the VAD.

        Args:
            aggressiveness: 0 (least aggressive) to 3 (most aggressive)
            sample_rate: Must be 8000, 16000, 32000, or 48000 Hz
        """
        if aggressiveness not in [0, 1, 2, 3]:
            raise ValueError("Aggressiveness must be 0-3")
        if sample_rate not in [8000, 16000, 32000, 48000]:
            raise ValueError("Sample rate must be 8000, 16000, 32000, or 48000")

        self.vad = webrtcvad.Vad(aggressiveness)
        self.sample_rate = sample_rate

    def is_speech(self, frame: bytes) -> bool:
        """
        Check if a single audio frame contains speech.

        Args:
            frame: 16-bit mono PCM audio bytes

        Returns:
            True if speech detected, False if silence
        """
        return self.vad.is_speech(frame, self.sample_rate)

    def process_chunk(self, audio_data: bytes, sample_rate: int = None) -> Tuple[bool, bytes]:
        """
        Process an audio chunk and determine if it contains significant speech.

        Args:
            audio_data: Raw 16-bit mono PCM audio bytes (required format for webrtcvad)
            sample_rate: Sample rate of the audio (defaults to instance sample_rate)

        Returns:
            Tuple of (contains_speech, concatenated_speech_frames)
        """
        if sample_rate is None:
            sample_rate = self.sample_rate

        # Split into frames for VAD processing
        # frame_size is in samples; convert to bytes (16-bit = 2 bytes/sample)
        frame_size_samples = int(sample_rate * 0.03)  # 30ms frames in samples
        frame_size_bytes = frame_size_samples * 2     # bytes per frame
        frames = []
        for i in range(0, len(audio_data), frame_size_bytes):
            frame = audio_data[i:i + frame_size_bytes]
            if len(frame) == frame_size_bytes:
                frames.append(frame)

        speech_frames = [f for f in frames if self.is_speech(f)]

        # Consider chunk as containing speech if > 30% of frames are speech
        speech_ratio = len(speech_frames) / len(frames) if frames else 0
        contains_speech = speech_ratio > 0.3

        return contains_speech, b"".join(speech_frames)


if __name__ == "__main__":
    # Simple test
    vad = VoiceActivityDetector(aggressiveness=2)
    print("VAD initialized with sample rate:", vad.sample_rate)