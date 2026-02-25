#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""LOC gate enforcement (PreToolUse hook).

Blocks edits when uncommitted LOC exceeds threshold.
Reads quality-state.json written by post_tool_quality.py.
"""

import json
import os
import sys

STATE_FILE = os.path.expanduser("~/.claude/quality-state.json")
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
