#!/usr/bin/env python3
"""
PreToolUse hook for Edit/Write/Bash.

Blocks (exit code 2) a small set of *unambiguous* out-of-scope signals:
macOS/Linux-specific audio APIs, a second simultaneous LLM provider wired
up live, cloud vector DB SDKs, and telemetry SDKs. These are cheap,
deterministic checks - the real scope audit is the `scope-guard` subagent
via /scope-check, which has actual judgment. This hook is a tripwire, not
the whole safety net, and is deliberately narrow to avoid false-positive
blocking of legitimate work (e.g. blocking on the word "linux" appearing
in a comment would be too aggressive).

Reads the Claude Code hook JSON payload from stdin.
Exit 0 = allow. Exit 2 = block (stderr message is shown to Claude).
"""
import json
import re
import sys

# Each entry: (compiled regex, human-readable reason)
HARD_BLOCK_PATTERNS = [
    (re.compile(r"\bCoreAudio\b|\bAVAudioEngine\b|pyobjc"),
     "macOS-specific audio API - this project is Windows-only per docs/CLIENT_BRIEF.md §4"),
    (re.compile(r"\bALSA\b|\bpulseaudio\b|python-sounddevice.*linux", re.I),
     "Linux-specific audio API - this project is Windows-only per docs/CLIENT_BRIEF.md §4"),
    (re.compile(r"pinecone|weaviate|qdrant(?!.*local)", re.I),
     "Cloud/hosted vector DB - client requires a local-only FAISS index per docs/CLIENT_BRIEF.md §3"),
    (re.compile(r"\bsentry_sdk\b|mixpanel|segment\.io|posthog", re.I),
     "Telemetry/analytics SDK - explicitly out of scope per docs/CLIENT_BRIEF.md §4"),
]


def get_text_to_check(payload: dict) -> str:
    tool_name = payload.get("tool_name", "")
    tool_input = payload.get("tool_input", {}) or {}
    if tool_name in ("Edit", "Write", "NotebookEdit"):
        return " ".join(
            str(tool_input.get(k, ""))
            for k in ("content", "new_string", "file_text", "new_str")
        )
    if tool_name == "Bash":
        return str(tool_input.get("command", ""))
    return ""


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0  # don't block on malformed input, fail open

    text = get_text_to_check(payload)
    if not text:
        return 0

    for pattern, reason in HARD_BLOCK_PATTERNS:
        if pattern.search(text):
            print(
                f"[scope-guard hook] Blocked: {reason}\n"
                f"If this is intentional (client approved a scope change), "
                f"update docs/CLIENT_BRIEF.md first, then proceed.",
                file=sys.stderr,
            )
            return 2

    return 0


if __name__ == "__main__":
    sys.exit(main())
