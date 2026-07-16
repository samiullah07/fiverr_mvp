"""Audio capture manager that ties together device enumeration, WASAPI capture,
VAD processing, and WebSocket streaming."""

import pyaudiowpatch as pyaudio  # Fixed import
import asyncio
import time
import logging
from typing import Callable, Optional
from .devices import enumerate_audio_devices, get_default_devices
from .vad import VoiceActivityDetector
from .ws import broadcast_audio_chunk, AudioChunk

logger = logging.getLogger(__name__)

class AudioManager:
    ...  # Same rest of the file as before