"""
Standalone test for AudioManager: runs live capture for ~10 seconds,
printing real-time stats per source (bytes received, VAD speech/silence
classification per chunk). Speak into the mic and play audio through
speakers during the run.
"""

import time
import sys
import threading

# Add parent to path for imports
sys.path.insert(0, "C:\\Users\\BEST LAPTOP\\Desktop\\meeting-copilot\\backend")

from audio.capture import AudioManager


def main():
    # Statistics tracking
    stats = {
        "mic_chunks": 0,
        "mic_bytes": 0,
        "mic_speech_chunks": 0,
        "mic_silence_chunks": 0,
        "loopback_chunks": 0,
        "loopback_bytes": 0,
        "loopback_speech_chunks": 0,
        "loopback_silence_chunks": 0,
    }
    stats_lock = threading.Lock()

    def on_speech(audio_bytes: bytes):
        """Callback that records when speech is detected."""
        pass

    # We need a callback that receives source info too.
    # The current AudioManager calls on_speech with just bytes.
    # To get per-source stats, we wrap the capture loops by subclassing.
    class TestAudioManager(AudioManager):
        def _mic_capture_loop(self, on_speech):
            try:
                while not self._stop_event.is_set():
                    try:
                        chunk_size = int(self._mic_info["defaultSampleRate"] * 0.1)
                        audio_bytes = self._mic_stream.read(chunk_size, exception_on_overflow=False)
                    except Exception as e:
                        if not self._stop_event.is_set():
                            print(f"Error reading microphone stream: {e}")
                        break

                    with stats_lock:
                        stats["mic_chunks"] += 1
                        stats["mic_bytes"] += len(audio_bytes)

                    mono_bytes = self._downmix_stereo_to_mono(
                        audio_bytes, self._mic_info.get("maxInputChannels", 2)
                    )
                    sample_rate = self._mic_info["defaultSampleRate"]
                    if sample_rate != 16000:
                        mono_bytes = self._resample_audio(mono_bytes, sample_rate, 16000)
                        sample_rate = 16000

                    contains_speech, speech_frames = self.vad_mic.process_chunk(
                        mono_bytes, sample_rate=sample_rate
                    )

                    with stats_lock:
                        if contains_speech:
                            stats["mic_speech_chunks"] += 1
                        else:
                            stats["mic_silence_chunks"] += 1

                    if contains_speech and speech_frames:
                        on_speech(speech_frames)

            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"Error in microphone capture loop: {e}")
            finally:
                print("Microphone capture loop ended")

        def _loopback_capture_loop(self, on_speech):
            print("[DEBUG] Loopback thread started")
            try:
                while not self._stop_event.is_set():
                    try:
                        chunk_size = int(self._loopback_info["defaultSampleRate"] * 0.1)
                        print(f"[DEBUG] Loopback reading {chunk_size} bytes...")
                        audio_bytes = self._loopback_stream.read(chunk_size, exception_on_overflow=False)
                        print(f"[DEBUG] Loopback read {len(audio_bytes)} bytes")
                    except Exception as e:
                        if not self._stop_event.is_set():
                            print(f"Error reading loopback stream: {e}")
                        break

                    with stats_lock:
                        stats["loopback_chunks"] += 1
                        stats["loopback_bytes"] += len(audio_bytes)

                    mono_bytes = self._downmix_stereo_to_mono(
                        audio_bytes, self._loopback_info.get("maxInputChannels", 2)
                    )
                    sample_rate = self._loopback_info["defaultSampleRate"]

                    contains_speech, speech_frames = self.vad_loopback.process_chunk(
                        mono_bytes, sample_rate=sample_rate
                    )

                    with stats_lock:
                        if contains_speech:
                            stats["loopback_speech_chunks"] += 1
                        else:
                            stats["loopback_silence_chunks"] += 1

                    if contains_speech and speech_frames:
                        on_speech(speech_frames)

            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"Error in loopback capture loop: {e}")
            finally:
                print("Loopback capture loop ended")

    manager = TestAudioManager()

    print("=" * 60)
    print("AudioManager Live Capture Test")
    print("=" * 60)
    print("Starting capture for 10 seconds...")
    print("ACTION: Speak into the microphone AND play audio through speakers")
    print("=" * 60)

    try:
        manager.start_capture(on_speech)
    except Exception as e:
        print(f"Failed to start capture: {e}")
        return

    # Run for 10 seconds, printing stats every 2 seconds
    start_time = time.time()
    next_print = start_time + 2.0

    while time.time() - start_time < 10.0:
        time.sleep(0.1)
        if time.time() >= next_print:
            with stats_lock:
                print(f"\n[{(time.time() - start_time):.1f}s] Stats:")
                print(f"  MIC:      chunks={stats['mic_chunks']:4d}  bytes={stats['mic_bytes']:8d}  "
                      f"speech={stats['mic_speech_chunks']:4d}  silence={stats['mic_silence_chunks']:4d}")
                print(f"  LOOPBACK: chunks={stats['loopback_chunks']:4d}  bytes={stats['loopback_bytes']:8d}  "
                      f"speech={stats['loopback_speech_chunks']:4d}  silence={stats['loopback_silence_chunks']:4d}")
            next_print += 2.0

    print("\n" + "=" * 60)
    print("Stopping capture...")
    manager.stop()

    with stats_lock:
        print("\nFinal Stats:")
        print(f"  MIC:      chunks={stats['mic_chunks']}  bytes={stats['mic_bytes']}  "
              f"speech={stats['mic_speech_chunks']}  silence={stats['mic_silence_chunks']}")
        print(f"  LOOPBACK: chunks={stats['loopback_chunks']}  bytes={stats['loopback_bytes']}  "
              f"speech={stats['loopback_speech_chunks']}  silence={stats['loopback_silence_chunks']}")
    print("=" * 60)


if __name__ == "__main__":
    main()