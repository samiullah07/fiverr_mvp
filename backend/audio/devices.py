"""Windows audio device enumeration using PyAudio with WASAPI."""

import pyaudiowpatch as pyaudio
from typing import List, Dict, Optional


def enumerate_audio_devices() -> Dict[str, List[Dict]]:
    """
    Enumerate all available audio devices on Windows.

    Returns:
        Dict with 'input' and 'output' keys, each containing a list of device info.
        Each device dict has: index, name, max_channels, default_sample_rate
    """
    p = pyaudio.PyAudio()

    try:
        # Dynamically look up the real WASAPI host API index.
        # PortAudio assigns hostApi indices per-machine based on what's installed,
        # so hardcoding 1 (the common-but-not-guaranteed WASAPI index) is wrong.
        wasapi_info = p.get_host_api_info_by_type(pyaudio.paWASAPI)
        wasapi_index = wasapi_info["index"]

        devices = {"input": [], "output": []}

        for i in range(p.get_device_count()):
            try:
                info = p.get_device_info_by_index(i)
                device_type = info.get("hostApi")

                # Filter for Windows WASAPI devices only
                # wasapi_index = the actual index this machine assigned to WASAPI
                if device_type == wasapi_index:
                    device = {
                        "index": i,
                        "name": info.get("name", ""),
                        "max_channels": info.get("maxInputChannels", 0) or info.get("maxOutputChannels", 0),
                        "defaultSampleRate": int(info.get("defaultSampleRate", 44100)),
                        "is_input": info.get("maxInputChannels", 0) > 0,
                        "is_output": info.get("maxOutputChannels", 0) > 0,
                        "isLoopbackDevice": info.get("isLoopbackDevice", False),
                        "maxInputChannels": info.get("maxInputChannels", 0),
                        "maxOutputChannels": info.get("maxOutputChannels", 0),
                    }

                    if device["is_input"]:
                        devices["input"].append(device)
                    if device["is_output"]:
                        devices["output"].append(device)

            except OSError:
                continue

        return devices

    finally:
        p.terminate()


def get_default_devices() -> Dict[str, Optional[Dict]]:
    """
    Get the default input (microphone) and output (system audio loopback) devices.

    Returns:
        Dict with 'mic' and 'loopback' keys for default devices.
        Values are None if not found.
    """
    devices = enumerate_audio_devices()

    # Default mic: first input device with " microphone" or " Microphone" in name
    # or first input device if no clear match
    default_mic = None
    for dev in devices["input"]:
        name_lower = dev["name"].lower()
        if "microphone" in name_lower or "mic" in name_lower:
            default_mic = dev
            break

    if default_mic is None and devices["input"]:
        default_mic = devices["input"][0]

    # Default loopback: first output device with " loopback" or "Loopback" in name
    # or first output device if no clear match
    default_loopback = None
    for dev in devices["output"]:
        name_lower = dev["name"].lower()
        if "loopback" in name_lower:
            default_loopback = dev
            break

    if default_loopback is None and devices["output"]:
        # Use first output device as fallback (will capture system audio)
        default_loopback = devices["output"][0]

    return {"mic": default_mic, "loopback": default_loopback}


if __name__ == "__main__":
    # Debug: list all devices
    import json
    print("=== Input Devices ===")
    for dev in enumerate_audio_devices()["input"]:
        print(f"  [{dev['index']}] {dev['name']}")

    print("\n=== Output Devices ===")
    for dev in enumerate_audio_devices()["output"]:
        print(f"  [{dev['index']}] {dev['name']}")

    print("\n=== Default Selection ===")
    defaults = get_default_devices()
    print(f"  Mic: {defaults['mic']['name'] if defaults['mic'] else 'NOT FOUND'}")
    print(f"  Loopback: {defaults['loopback']['name'] if defaults['loopback'] else 'NOT FOUND'}")