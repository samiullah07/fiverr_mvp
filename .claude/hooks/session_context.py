#!/usr/bin/env python3
"""
SessionStart hook.

Prints a short status banner (as additional context) reminding whoever
starts the session where things stand: last git activity, and a pointer
back to docs/CLIENT_BRIEF.md and docs/PROJECT_PLAN.md. This is purely
informational - it cannot block anything.
"""
import subprocess
import sys


def run(cmd):
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=5
        ).stdout.strip()
    except Exception:
        return ""


def main() -> int:
    last_commit = run(["git", "log", "-1", "--format=%h %s (%cr)"])
    changed = run(["git", "status", "--porcelain"])
    changed_count = len(changed.splitlines()) if changed else 0

    lines = [
        "Meeting Copilot project — reminders:",
        "- Scope contract: docs/CLIENT_BRIEF.md (read before changing scope)",
        "- Phase plan: docs/PROJECT_PLAN.md",
    ]
    if last_commit:
        lines.append(f"- Last commit: {last_commit}")
    if changed_count:
        lines.append(f"- {changed_count} uncommitted file(s) in working tree")

    print("\n".join(lines))
    return 0


if __name__ == "__main__":
    sys.exit(main())
