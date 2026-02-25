#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Track LOC changes for quality gate enforcement (PostToolUse hook).

Counts lines changed via git diff --stat HEAD and updates quality-state.json.
Resets when no uncommitted changes exist (i.e., after a commit).
"""

import json
import os
import subprocess
import sys

STATE_FILE = os.path.expanduser("~/.claude/quality-state.json")


def get_loc_since_commit() -> int:
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return 0

        # Last line of git diff --stat is like: "5 files changed, 120 insertions(+), 30 deletions(-)"
        lines = result.stdout.strip().split("\n")
        if not lines:
            return 0

        summary = lines[-1]
        insertions = 0
        deletions = 0
        for part in summary.split(","):
            part = part.strip()
            if "insertion" in part:
                insertions = int(part.split()[0])
            elif "deletion" in part:
                deletions = int(part.split()[0])

        return insertions + deletions
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return 0


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    file_path = data.get("tool_input", {}).get("file_path", "")
    loc = get_loc_since_commit()

    state = load_state()
    state["locSinceCommit"] = loc
    state["lastFile"] = file_path
    save_state(state)


if __name__ == "__main__":
    main()
