#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Quality gate enforcer (PreToolUse hook).

Blocks edit operations when a quality gate is active.
Reads quality-state-{hash}.json written by post_tool_quality.py.

Gate types:
  refactor      — must complete refactor step after feat: commit
  phase:{name}  — must commit phase transition and read phase instructions
"""

import hashlib
import json
import os
import subprocess
import sys

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

PHASE_FILES = {
    "intake": "DISCOVERY.md",
    "define-behavior": "SCENARIOS.md",
    "scenario-gate": "SCENARIOS.md",
    "decomposition": "DECOMPOSITION.md",
    "implement": "TDD.md",
    "done": "DONE.md",
}
SKILLS_DIR = os.path.expanduser("~/.claude/skills/bdd-orchestrating")


def _state_file() -> str:
    """Worktree-aware state file path."""
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


def load_state() -> dict:
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def get_head_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def read_phase_file(phase: str) -> str:
    """Read the BDD phase skill file content."""
    filename = PHASE_FILES.get(phase)
    if not filename:
        return ""
    filepath = os.path.join(SKILLS_DIR, filename)
    try:
        with open(filepath) as f:
            return f.read()
    except (FileNotFoundError, OSError):
        return ""


def deny(reason: str):
    """Output a structured denial and exit."""
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        sys.stdout,
    )
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    # Only gate edit tools — Read, Glob, Grep, Bash pass through
    if data.get("tool_name") not in EDIT_TOOLS:
        sys.exit(0)

    state = load_state()
    gate = state.get("gate")
    if not gate:
        sys.exit(0)

    # Freshness check: if HEAD changed since gate was set, gate is stale
    current_head = get_head_hash()
    stored_head = state.get("lastCommitHash", "")
    if current_head and stored_head and current_head != stored_head:
        sys.exit(0)

    # --- Gate-specific denial messages ---

    if gate == "refactor":
        deny(
            "Refactor gate: Complete the RED \u2192 GREEN \u2192 REFACTOR cycle.\n\n"
            "You committed a feat: change. Before writing more code:\n"
            "1. Evaluate refactoring opportunities (duplication, naming, structure)\n"
            "2. If changes needed: make them, then commit: refactor: {{description}}\n"
            "3. If no changes needed: git commit --allow-empty -m 'refactor: no changes needed'\n\n"
            "The gate clears on the next commit."
        )

    elif gate.startswith("phase:"):
        phase = gate.split(":", 1)[1]
        phase_content = read_phase_file(phase)
        msg = (
            f"Phase gate: Entering '{phase}' phase.\n"
            "Commit the phase transition before continuing.\n"
        )
        if phase_content:
            if len(phase_content) > 3000:
                phase_content = phase_content[:3000] + "\n\n[... truncated]"
            msg += f"\nPhase instructions:\n\n{phase_content}"
        deny(msg)

    else:
        deny(f"Quality gate active: {gate}. Commit to clear.")


if __name__ == "__main__":
    main()
