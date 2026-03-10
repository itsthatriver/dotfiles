#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""LOC gate enforcement (PreToolUse hook).

Blocks edits when uncommitted LOC exceeds threshold.
Reads quality-state.json written by post_tool_quality.py.
"""

import hashlib
import json
import os
import subprocess
import sys


def _state_file() -> str:
    """Worktree-aware state file path to avoid collisions across parallel worktrees."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode == 0:
            tree = result.stdout.strip()
            suffix = hashlib.sha256(tree.encode()).hexdigest()[:12]
            return os.path.expanduser(f"~/.claude/quality-state-{suffix}.json")
    except (subprocess.TimeoutExpired, OSError):
        pass
    return os.path.expanduser("~/.claude/quality-state.json")


STATE_FILE = _state_file()
LOC_THRESHOLD = 400


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def main():
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        pass

    state = load_state()
    loc = state.get("locSinceCommit", 0)

    if loc >= LOC_THRESHOLD:
        print(
            f"LOC threshold exceeded ({loc}/{LOC_THRESHOLD} lines changed). "
            "Commit your changes before continuing. "
            "Small, atomic commits enable agent handoffs — "
            "the commit log IS the context transfer mechanism.",
            file=sys.stderr,
        )
        sys.exit(2)


if __name__ == "__main__":
    main()
