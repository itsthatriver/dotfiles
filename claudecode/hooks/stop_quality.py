#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Quality review prompt when Claude finishes responding (Stop hook).

Checks if edits were made during the response and prints a quality
review reminder. Soft enforcement — guides but does not block.
"""

import json
import sys

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    # The stop hook receives the last assistant message and session context
    # Check if the session involved edit operations
    stop_active = data.get("stop_hook_active", False)
    if not stop_active:
        sys.exit(0)

    print(
        "Quality check: Before finishing, verify — "
        "(1) Do changes follow the methodology (patch/task/feature)? "
        "(2) Are there tests for new behavior? "
        "(3) Is there unreferenced code to clean up? "
        "(4) Are commit messages descriptive enough for agent handoff?"
    )


if __name__ == "__main__":
    main()
