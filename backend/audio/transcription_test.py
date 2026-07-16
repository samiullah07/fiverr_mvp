"""
Standalone test for AudioManager with real-time transcription.

Runs live capture with faster-whisper transcription for ~15 seconds,
printing transcribed text as it appears. Speak into the mic during the run.

IMPORTANT: This test uses the REAL faster-whisper model. The transcribed
output shown here is the actual model output - not simulated.
"""

import time
import sys
import threading
import datetime

# Add parent to path for imports
sys.path.insert(0, "C:\\Users\\BEST LAPTOP\\Desktop\\meeting-copilot\\backend")

from audio.capture import AudioManager


def main():
    transcriptions = []
    transcriptions_lock = threading.Lock()
    test_start = time.time()

    def on_transcript(text: str, latency: float):
        """Callback when transcription produces text."""
        with transcriptions_lock:
            current_time = datetime.datetime.now().strftime("%H:%M:%S.%f")
            ts = time.time() - test_start
            transcriptions.append((current_time, text, latency))
            print(f"\n[{current_time}] [TRANSCRIPT] {text}  (whisper: {latency:.2f}s, elapsed: {ts:.2f}s)")

    def on_speech(audio_bytes: bytes):
        """Callback that receives speech audio (also fed to transcriber)."""
        pass  # Transcriber gets audio via internal callback

    print("=" * 70)
    print("AudioManager + faster-whisper Transcription Test")
    print("=" * 70)
    print("Model: tiny.en (int8 on CPU)")
    print("Buffer target: 1.5s | Overlap: 0.3s")
    print("Target latency: ~2-2.5s from speech to transcript")
    print("=" * 70)

    # Create manager with transcription enabled
    manager = AudioManager(enable_transcription=True)

    # Override transcriber callback
    if manager.transcriber:
        manager.transcriber.on_transcript = on_transcript

    # Add timestamp to "Speak now!" prompt
    speak_now_time = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"\n[{speak_now_time}] Speak now!\n")

    # Run for 12 seconds to account for any unexpected delays
    test_duration = 12.0

    try:
        manager.start_capture(on_speech)
    except Exception as e:
        print(f"Failed to start capture: {e}")
        return

    time.sleep(test_duration)

    print(f"\n[{datetime.datetime.now().strftime('%H:%M:%S')}] Stopping capture...\n")
    manager.stop()

    # Wait for threads to finish (does not use lock to avoid deadlock)
    if manager.transcriber:
        manager.transcriber.stop()
    manager._stop_event.set()

    # Final summary
    print("=" * 70)
    if transcriptions:
        for i, (current_time, text, latency) in enumerate(transcriptions, 1):
            print(f"  {i}. [{current_time}] {text}  (latency: {latency:.2f}s)")
    else:
        print("  No transcriptions captured - check your audio input")
    print("=" * 70)
    print("Test completed successfully!")


if __name__ == "__main__":
    main()