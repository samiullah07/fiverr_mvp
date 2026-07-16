"""Smoke test for pyaudiowpatch WASAPI loopback capture."""

import pyaudiowpatch as pyaudio

# Step 1: Verify the import
print(f"pyaudiowpatch location: {pyaudio.__file__}")
print(f"pyaudiowpatch version: {pyaudio.__version__ if hasattr(pyaudio, '__version__') else 'unknown'}")

# Step 2: Open PyAudio instance
pa = pyaudio.PyAudio()

# Step 3: Find WASAPI loopback devices using the isLoopbackDevice flag
print("\nLooking for WASAPI loopback devices...")
loopback_devices = []
for i in range(pa.get_device_count()):
    try:
        info = pa.get_device_info_by_index(i)
        name = info.get('name', '')
        is_loopback = info.get('isLoopbackDevice', False)
        if is_loopback:
            loopback_devices.append((i, info))  # keep full info for later
            print(f"  Found WASAPI loopback: index={i}, name={name}")
    except Exception as e:
        print(f"  Error getting device {i}: {e}")

if not loopback_devices:
    print("ERROR: No WASAPI loopback devices found!")
    pa.terminate()
    exit(1)

# Use the first loopback device
device_index, device_info = loopback_devices[0]
device_name = device_info.get('name', '')
print(f"\nUsing device index {device_index}: {device_name}")

# Step 4: Open stream on loopback device as INPUT
# WASAPI loopback must use the device's own maxInputChannels (usually 2, stereo)
# per PyAudioWPatch's official example; channels=1 was rejected with -9996.
# Use paInt16 (not paFloat32): webrtcvad needs 16-bit PCM anyway.
sample_rate = int(device_info.get('defaultSampleRate', 44100))
channels = int(device_info.get('maxInputChannels', 2))
frames_per_buffer = int(sample_rate * 2)  # 2 seconds

print(f"\nDevice default sample rate: {sample_rate}")
print(f"Device maxInputChannels: {channels}")
print(
    f"Opening stream with: format=paInt16, "
    f"channels={channels}, rate={sample_rate}, frames_per_buffer={frames_per_buffer}"
)

stream = pa.open(
    format=pyaudio.paInt16,
    channels=channels,
    rate=sample_rate,
    input=True,
    input_device_index=device_index,
    frames_per_buffer=frames_per_buffer,
)

# Step 5: Read one chunk and print results
print("\nReading audio chunk...")
try:
    data = stream.read(frames_per_buffer, exception_on_overflow=False)
    print(f"Read {len(data)} bytes")
    expected_bytes = frames_per_buffer * channels * 2  # 16-bit = 2 bytes/sample
    print(f"Expected bytes (frames_per_buffer * channels * 2): {expected_bytes}")
    print(f"First 20 bytes (hex): {data[:20].hex()}")
except Exception as e:
    print(f"ERROR reading stream: {e}")
finally:
    stream.stop_stream()
    stream.close()
    pa.terminate()
    print("\nDone.")