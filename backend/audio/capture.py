import time
import pyaudiowpatch as pyaudio
import numpy as np
from scipy.signal import resample_poly
from typing import Callable, Optional
import threading
from threading import Thread, Event

from .vad import VoiceActivityDetector
from .devices import enumerate_audio_devices
from .transcription import WhisperTranscriber


class AudioManager:
    """
    Audio capture manager for Windows meeting copilot.
    Handles microphone and system audio loopback capture with VAD preprocessing.

    Key features:
    - Device selection via substring matching (no hardcoded indices)
    - Stereo to mono downmixing for both streams
    - 44100 Hz microphone -> 16000 Hz resampling (VAD compatible)
    - 48000 Hz loopback (already VAD compatible)
    - Per-chunk sample rate information for both streams
    - Clean error handling and logging
    - Thread-safe start/stop
    """

    def __init__(self, mic_aggressiveness: int = 2, loopback_aggressiveness: int = 2, enable_transcription: bool = False):
        """
        Initialize audio capture manager.

        Args:
            mic_aggressiveness: VAD aggressiveness for microphone (0-3)
            loopback_aggressiveness: VAD aggressiveness for loopback (0-3)
            enable_transcription: If True, enables real-time transcription with faster-whisper
        """
        self.vad_mic = VoiceActivityDetector(aggressiveness=mic_aggressiveness, sample_rate=16000)
        self.vad_loopback = VoiceActivityDetector(aggressiveness=loopback_aggressiveness, sample_rate=48000)
        self._stop_event = Event()
        self._mic_thread: Optional[Thread] = None
        self._loopback_thread: Optional[Thread] = None
        self._pa: Optional[pyaudio.PyAudio] = None  # Single PyAudio instance reused
        self._mic_stream = None
        self._loopback_stream = None
        self._mic_info = None
        self._loopback_info = None

        # Transcription components (optional)
        self.enable_transcription = enable_transcription
        self.transcriber: Optional[WhisperTranscriber] = None
        if enable_transcription:
            self.transcriber = WhisperTranscriber()

    def _get_device_matching_condition(self, device_name: str) -> bool:
        """
        Device selection criteria using substring matching.

        Args:
            device_name: Name of the audio device to evaluate

        Returns:
            True if device matches selection criteria, False otherwise
        """
        if not device_name:
            return False

        name_lower = device_name.lower()

        # Prefer physical Intel Smart Sound Technology microphones
        if "intel" in name_lower and "smart sound technology" in name_lower:
            return True

        # Physical microphones generally preferred over virtual ones
        is_physical = any(term in name_lower for term in ["microphone", "mic", "array", "primary", "sound"])
        if is_physical:
            return True

        # Virtual devices are fallback options
        return False

    def _select_microphone_device(self, devices: dict) -> tuple:
        """
        Select microphone device based on preference criteria.

        Args:
            devices: Dictionary with 'input' and 'output' device lists from enumerate_audio_devices()

        Returns:
            Tuple of (device_index, device_info) or (None, None) if no input devices
        """
        input_devices = devices.get("input", [])
        if not input_devices:
            return None, None

        # Filter for preferred devices
        preferred = []
        for device in input_devices:
            if self._get_device_matching_condition(device["name"]):
                preferred.append(device)

        if preferred:
            # Among preferred, choose the one with maxInputChannels == 2 (normal mic)
            preferred_mono = [d for d in preferred if d.get("maxInputChannels", 0) == 2]
            if preferred_mono:
                chosen = preferred_mono[0]
                reason = "preferred physical mic with maxInputChannels=2 (normal mic)"
            else:
                chosen = preferred[0]
                reason = "preferred physical mic (only 4-channel variant available)"
            print(f"  Selected microphone: {chosen['name']} (index {chosen['index']})")
            print(f"  Reason: {reason}")
            return chosen["index"], chosen
        else:
            # Fallback to first input device
            chosen = input_devices[0]
            print(f"  Selected microphone (fallback): {chosen['name']} (index {chosen['index']})")
            print(f"  Reason: no preferred device found, using first available")
            return chosen["index"], chosen

    def _select_loopback_device(self, devices: dict) -> tuple:
        """
        Select loopback device using isLoopbackDevice flag from device info.

        Args:
            devices: Dictionary with 'input' and 'output' device lists from enumerate_audio_devices()
                   Each device dict MUST include 'isLoopbackDevice' boolean flag

        Returns:
            Tuple of (device_index, device_info) or (None, None) if no loopback device found
        """
        # Check both input and output devices for loopback capability using isLoopbackDevice flag
        all_devices = devices.get("input", []) + devices.get("output", [])
        loopback_devices = [d for d in all_devices if d.get("isLoopbackDevice", False)]

        if loopback_devices:
            chosen = loopback_devices[0]
            print(f"  Selected loopback: {chosen['name']} (index {chosen['index']}) [isLoopbackDevice=True]")
            return chosen["index"], chosen
        else:
            print(f"  No loopback device found with isLoopbackDevice=True")
            return None, None

    def _downmix_stereo_to_mono(self, audio_bytes: bytes, channels: int) -> bytes:
        """
        Convert multichannel interleaved PCM to mono.

        For stereo (2 channels): average left + right -> mono.
        For >2 channels (e.g., 4-mic array): take channel 0 only.
        Averaging a 4-mic array smears the signal and hurts intelligibility.

        Args:
            audio_bytes: Raw audio bytes in interleaved PCM format
            channels: Number of channels in the audio (1 for mono, 2 for stereo, etc.)

        Returns:
            16-bit mono audio bytes
        """
        if channels <= 1:
            return audio_bytes

        # Convert to numpy array
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

        # Reshape interleaved PCM: (-1, channels) then extract mono
        audio_array = audio_array.reshape((-1, channels))

        if channels > 2:
            # Multi-channel array (e.g., 4-mic): take channel 0 only.
            mono_array = audio_array[:, 0]
        else:
            # Stereo: average both channels
            mono_array = np.mean(audio_array, axis=1, dtype=np.int16)

        return mono_array.tobytes()

    def _resample_audio(self, audio_bytes: bytes, original_sample_rate: int,
                       target_sample_rate: int) -> bytes:
        """
        Resample audio to target sample rate using scipy.signal.resample_poly.

        Args:
            audio_bytes: Audio bytes to resample (16-bit PCM)
            original_sample_rate: Current sample rate of the audio
            target_sample_rate: Desired sample rate (must be in [8000, 16000, 32000, 48000] for VAD)

        Returns:
            Resampled audio bytes (16-bit PCM)
        """
        if original_sample_rate == target_sample_rate:
            return audio_bytes

        # Convert to numpy array
        audio_array = np.frombuffer(audio_bytes, dtype=np.int16)

        # Resample using polyphase filtering (provides anti-aliasing)
        resampled_array = resample_poly(
            audio_array,
            up=target_sample_rate,
            down=original_sample_rate
        )

        # Convert back to int16 bytes with clipping to prevent overflow
        resampled_array = np.clip(resampled_array, -32768, 32767).astype(np.int16)

        return resampled_array.tobytes()

    def _mic_capture_loop(self, on_speech: Callable[[bytes], None]):
        """
        Background thread for microphone capture and processing.
        Reads from already-open stream repeatedly (not opening new stream each chunk).
        """
        try:
            while not self._stop_event.is_set():
                # Read from already-open stream (opened once in start_capture)
                try:
                    # Read 100ms chunks from persistent stream
                    chunk_size = int(self._mic_info.get("defaultSampleRate", 44100) * 0.1)
                    audio_bytes = self._mic_stream.read(chunk_size, exception_on_overflow=False)
                except Exception as e:
                    if not self._stop_event.is_set():
                        print(f"Error reading microphone stream: {e}")
                    break

                # Process audio: downmix to mono
                mono_bytes = self._downmix_stereo_to_mono(
                    audio_bytes,
                    self._mic_info.get("maxInputChannels", 2)
                )

                # Resample to VAD rate if needed
                sample_rate = self._mic_info.get("defaultSampleRate", 44100)
                if sample_rate != 16000:
                    mono_bytes = self._resample_audio(mono_bytes, sample_rate, 16000)
                    sample_rate = 16000

                # Process with VAD
                contains_speech, speech_frames = self.vad_mic.process_chunk(
                    mono_bytes, sample_rate=sample_rate
                )

                if contains_speech and speech_frames:
                    on_speech(speech_frames)

        except Exception as e:
            if not self._stop_event.is_set():
                print(f"Error in microphone capture loop: {e}")
        finally:
            print("Microphone capture loop ended")

    def _loopback_capture_loop(self, on_speech: Callable[[bytes], None]):
        """
        Background thread for loopback capture and processing.
        Reads from already-open stream repeatedly (not opening new stream each chunk).
        """
        try:
            while not self._stop_event.is_set():
                # Read from already-open stream (opened once in start_capture)
                try:
                    # Read 100ms chunks from persistent stream
                    chunk_size = int(self._loopback_info.get("defaultSampleRate", 48000) * 0.1)
                    audio_bytes = self._loopback_stream.read(chunk_size, exception_on_overflow=False)
                except Exception as e:
                    if not self._stop_event.is_set():
                        print(f"Error reading loopback stream: {e}")
                    break

                # Process audio: downmix to mono using maxInputChannels (stream is input)
                mono_bytes = self._downmix_stereo_to_mono(
                    audio_bytes,
                    self._loopback_info.get("maxInputChannels", 2)  # Use maxInputChannels, not maxOutputChannels
                )

                # Loopback is already at 48000 Hz (VAD compatible)
                sample_rate = self._loopback_info.get("defaultSampleRate", 48000)

                # Process with VAD
                contains_speech, speech_frames = self.vad_loopback.process_chunk(
                    mono_bytes, sample_rate=sample_rate
                )

                if contains_speech and speech_frames:
                    on_speech(speech_frames)

        except Exception as e:
            if not self._stop_event.is_set():
                print(f"Error in loopback capture loop: {e}")
        finally:
            print("Loopback capture loop ended")

    def start_capture(self, on_speech: Callable[[bytes], None]):
        """
        Start audio capture for both microphone and system audio.
        Opens streams once and reuses them (not opening/closing every ~100ms).

        Args:
            on_speech: Callback function to process speech audio (receives bytes of 16-bit mono PCM)
        """
        print("Initializing AudioManager...")

        # Get all audio devices
        devices = enumerate_audio_devices()
        if not devices:
            raise RuntimeError("Failed to enumerate audio devices")

        # Select microphone device
        mic_index, self._mic_info = self._select_microphone_device(devices)
        if mic_index is None:
            raise RuntimeError("No microphone devices available")

        # Select loopback device
        loopback_index, self._loopback_info = self._select_loopback_device(devices)
        if loopback_index is None:
            raise RuntimeError("No loopback devices available - check microphone/speaker configuration")

        print(f"\nCapture configuration:")
        print(f"  Microphone: {self._mic_info.get('name', 'Unknown')} "
              f"(rate: {self._mic_info.get('defaultSampleRate', 16000)} Hz, "
              f"channels: {self._mic_info.get('maxInputChannels', 1)})")
        print(f"  Loopback: {self._loopback_info.get('name', 'Unknown')} "
              f"(rate: {self._loopback_info.get('defaultSampleRate', 48000)} Hz, "
              f"channels: {self._loopback_info.get('maxInputChannels', 1)})")

        # Initialize PyAudio and open streams ONCE (reuse single instance)
        try:
            self._pa = pyaudio.PyAudio()  # Single PyAudio instance

            # Open microphone stream ONCE
            self._mic_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=self._mic_info.get("maxInputChannels", 2),
                rate=int(self._mic_info.get("defaultSampleRate", 44100)),
                input=True,
                input_device_index=mic_index,
                frames_per_buffer=int(self._mic_info.get("defaultSampleRate", 44100) * 0.1),  # 100ms
                stream_callback=None  # blocking read mode
            )

            # Open loopback stream ONCE (input stream uses maxInputChannels)
            self._loopback_stream = self._pa.open(
                format=pyaudio.paInt16,
                channels=self._loopback_info.get("maxInputChannels", 2),  # Use maxInputChannels for input stream
                rate=int(self._loopback_info.get("defaultSampleRate", 48000)),
                input=True,
                input_device_index=loopback_index,
                frames_per_buffer=int(self._loopback_info.get("defaultSampleRate", 48000) * 0.1),  # 100ms
                stream_callback=None  # blocking read mode
            )

            print("\nAudio streams opened successfully (reused for all reads)")

            # Start transcriber if enabled
            if self.transcriber:
                self.transcriber.start()
                # Create wrapper callback that feeds both user callback and transcriber
                def transcription_callback(audio_bytes: bytes):
                    on_speech(audio_bytes)
                    self.transcriber.feed_audio(audio_bytes)
                self._mic_thread = Thread(target=self._mic_capture_loop, args=(transcription_callback,), daemon=True)
                self._loopback_thread = Thread(target=self._loopback_capture_loop, args=(transcription_callback,), daemon=True)
            else:
                self._mic_thread = Thread(target=self._mic_capture_loop, args=(on_speech,), daemon=True)
                self._loopback_thread = Thread(target=self._loopback_capture_loop, args=(on_speech,), daemon=True)

            self._mic_thread.start()
            self._loopback_thread.start()

            print("Background capture threads started")

        except Exception as e:
            print(f"Failed to start audio capture: {e}")
            self.stop()
            raise

    def stop(self):
        """
        Stop audio capture and clean up resources.
        Thread-safe - can be called from outside (e.g., from an event or shared flag).
        """
        print("Stopping audio capture...")
        self._stop_event.set()

        # Close streams FIRST to unblock read() calls in capture threads
        if self._mic_stream:
            try:
                self._mic_stream.stop_stream()
                self._mic_stream.close()
            except Exception as e:
                print(f"Error closing microphone stream: {e}")
            self._mic_stream = None

        if self._loopback_stream:
            try:
                self._loopback_stream.stop_stream()
                self._loopback_stream.close()
            except Exception as e:
                print(f"Error closing loopback stream: {e}")
                try:
                    import traceback
                    traceback.print_exc()
                except:
                    pass
            self._loopback_stream = None

        # Stop transcriber if present
        if self.transcriber:
            try:
                self.transcriber.stop()
            except Exception as e:
                print(f"Error stopping transcriber: {e}")
                try:
                    import traceback
                    traceback.print_exc()
                except:
                    pass

        # NOW wait for threads to finish (streams are closed, reads will return)
        if self._mic_thread and self._mic_thread.is_alive():
            self._mic_thread.join(timeout=2.0)
        if self._loopback_thread and self._loopback_thread.is_alive():
            self._loopback_thread.join(timeout=2.0)

        # Terminate PyAudio
        if self._pa:
            try:
                self._pa.terminate()
            except Exception as e:
                print(f"Error terminating PyAudio: {e}")
            self._pa = None

        print("Audio capture stopped")