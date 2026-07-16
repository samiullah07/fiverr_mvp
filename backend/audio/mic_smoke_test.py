"""Smoke test for microphone input capture."""

import pyaudiowpatch as pyaudio
import numpy as np
import time

# Step 1: Verify the import
print(f"pyaudiowpatch location: {pyaudio.__file__}")
print(f"pyaudiowpatch version: {pyaudio.__version__ if hasattr(pyaudio, '__version__') else 'unknown'}")

# Step 2: Open PyAudio instance
pa = pyaudio.PyAudio()

# Step 3: Find microphone devices (not loopback)
print("\nLooking for microphone devices...")
mic_devices = []
for i in range(pa.get_device_count()):
    try:
        info = pa.get_device_info_by_index(i)
        name = info.get("name", "")
        is_loopback = info.get("isLoopbackDevice", False)
        is_input = info.get("maxInputChannels", 0) > 0
        if is_input and not is_loopback:
            mic_devices.append((i, info))  # keep full info for later
            print(f"  Found microphone: index={i}, name={name}, maxInputChannels={info.get('maxInputChannels', 0)}")
    except Exception as e:
        print(f"  Error getting device {i}: {e}")

if not mic_devices:
    print("ERROR: No microphone devices found!")
    pa.terminate()
    exit(1)

# Prefer physical Intel Smart Sound Technology microphone.
# Match on substrings that avoid the special character in the device name:
# require BOTH "Intel" and "Smart Sound Technology" to appear.
preferred_indices = [
    i for i, d in enumerate(mic_devices)
    if "Intel" in d[1].get("name", "") and "Smart Sound Technology" in d[1].get("name", "")
]
if preferred_indices:
    # Among preferred physical mics, prefer maxInputChannels == 2 (normal mono/stereo mic),
    # not the 4-channel array variant, unless only the 4-channel variant exists.
    preferred_mono = [i for i in preferred_indices if mic_devices[i][1].get("maxInputChannels", 0) == 2]
    if preferred_mono:
        chosen_idx = preferred_mono[0]
        reason = "preferred physical mic with maxInputChannels=2 (normal mic)"
    else:
        chosen_idx = preferred_indices[0]
        reason = "preferred physical mic (only 4-channel variant available)"
    mic_index, mic_info = mic_devices[chosen_idx]
else:
    # Fall back to first device (virtual mapper) only if no physical mic found
    mic_index, mic_info = mic_devices[0]
    reason = "no physical Intel mic found, falling back to first device"
mic_name = mic_info.get("name", "")
print(f"\nUsing microphone index {mic_index}: {mic_name}")
print(f"  Selection reason: {reason}")

# 3-second countdown to allow user to prepare
print("\nRecording in 3...")
import time; time.sleep(1)
print("Recording in 2...")
time.sleep(1)
print("Recording in 1...")
time.sleep(1)
print("SPEAK NOW")

# Step 4: Open stream on microphone device as INPUT
sample_rate = int(mic_info.get("defaultSampleRate", 44100))
channels = int(mic_info.get("maxInputChannels", 2))
frames_per_buffer = int(sample_rate * 2)  # 2 seconds

print(f"\nMicrophone default sample rate: {sample_rate}")
print(f"Microphone maxInputChannels: {channels}")
print(
    f"Opening stream with: format=paInt16, "
    f"channels={channels}, rate={sample_rate}, frames_per_buffer={frames_per_buffer}"
)

stream = pa.open(
    format=pyaudio.paInt16,
    channels=channels,
    rate=sample_rate,
    input=True,
    input_device_index=mic_index,
    frames_per_buffer=frames_per_buffer,
)

# Step 5: Read one chunk and print results
print("\nReading microphone audio chunk...")
try:
    data = stream.read(frames_per_buffer, exception_on_overflow=False)
    print(f"Read {len(data)} bytes")
    expected_bytes = frames_per_buffer * channels * 2  # 16-bit = 2 bytes/sample
    print(f"Expected bytes (frames_per_buffer * channels * 2): {expected_bytes}")
    if len(data) == expected_bytes:
        print("[OK] Byte count matches expected formula")
    else:
        print("[FAIL] Byte count MISMATCH from expected formula")
    print(f"First 20 bytes (hex): {data[:20].hex()}")
    hex_preview = data[:20].hex()
    if len(hex_preview) >= 40 and any(c != '0' for c in hex_preview):
        print("[OK] Non-trivial hex data - microphone is working")
    else:
        print("[WARN] Data appears to be all zeros or very quiet")

    # Convert buffer to numpy int16 array and report max absolute sample value
    samples = np.frombuffer(data, dtype=np.int16)
    max_abs = int(np.abs(samples).max())
    print(f"Max absolute sample value (int16): {max_abs}")
    if max_abs < 1000:
        print("[WARN] Near-silence - mic may not be capturing real audio")
    else:
        print("[OK] Strong signal detected - real audio captured")
except Exception as e:
    print(f"ERROR reading stream: {e}")
finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()
    print("\nDone.")