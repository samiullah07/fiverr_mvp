#!/usr/bin/env python3
"""
PostToolUse hook for Edit/Write.

Best-effort auto-format of the file that was just touched:
- .py files -> black + ruff --fix, if installed
- .ts/.tsx/.js/.jsx files -> prettier, if installed

Never fails the tool call over a missing formatter - this is a convenience,
not an enforcement hook (that's scope_guard.py's job). Always exits 0.
"""
import json
import shutil
import subprocess
import sys


def main() -> int:
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return 0

    tool_input = payload.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path") or tool_input.get("path")
    if not file_path:
        return 0

    try:
        if file_path.endswith(".py"):
            if shutil.which("black"):
                subprocess.run(["black", "-q", file_path], check=False)
            if shutil.which("ruff"):
                subprocess.run(["ruff", "check", "--fix", "-q", file_path], check=False)
        elif file_path.endswith((".ts", ".tsx", ".js", ".jsx")):
            if shutil.which("prettier"):
                subprocess.run(["prettier", "--write", file_path], check=False)
    except Exception as e:
        # Never block the session over a formatter hiccup.
        print(f"[format hook] non-fatal: {e}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())
