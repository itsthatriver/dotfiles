#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Quality state observer (PostToolUse hook).

Tracks LOC, detects commits and phase transitions, and sets enforcement gates.
Writes quality-state-{hash}.json consumed by pre_tool_quality.py and stop_quality.py.

Gate types:
  loc           — uncommitted LOC >= 400
  refactor      — feat: commit during implement phase, must refactor before continuing
  phase:{name}  — BDD phase transition, must commit and read phase instructions
"""

import glob
import hashlib
import json
import os
import re
import subprocess
import sys

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}
RELEVANT_TOOLS = EDIT_TOOLS | {"Bash"}
LOC_THRESHOLD = 400


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


def save_state(state: dict):
    os.makedirs(os.path.dirname(STATE_FILE), exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def get_head_hash() -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def get_last_commit_message() -> str:
    try:
        result = subprocess.run(
            ["git", "log", "-1", "--format=%s"],
            capture_output=True, text=True, timeout=5,
        )
        return result.stdout.strip() if result.returncode == 0 else ""
    except (subprocess.TimeoutExpired, OSError):
        return ""


def get_loc_since_commit() -> int:
    try:
        result = subprocess.run(
            ["git", "diff", "--stat", "HEAD"],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return 0
        lines = result.stdout.strip().split("\n")
        if not lines or not lines[-1].strip():
            return 0
        summary = lines[-1]
        insertions = deletions = 0
        for part in summary.split(","):
            part = part.strip()
            if "insertion" in part:
                insertions = int(part.split()[0])
            elif "deletion" in part:
                deletions = int(part.split()[0])
        return insertions + deletions
    except (subprocess.TimeoutExpired, OSError, ValueError):
        return 0


def read_ticket_phase(file_path: str) -> str | None:
    """Extract phase from ticket.md YAML frontmatter."""
    try:
        with open(file_path) as f:
            content = f.read(2048)
        match = re.match(r"^---\s*\n(.*?)\n---", content, re.DOTALL)
        if not match:
            return None
        for line in match.group(1).split("\n"):
            stripped = line.strip()
            if stripped.startswith("phase:"):
                return stripped.split(":", 1)[1].strip()
    except (FileNotFoundError, OSError):
        pass
    return None


def find_active_ticket(cwd: str) -> tuple[str | None, str | None]:
    """Find the most recently modified ticket.md and its phase."""
    ticket_dir = os.path.join(cwd, ".project", "tickets")
    if not os.path.isdir(ticket_dir):
        return None, None
    pattern = os.path.join(ticket_dir, "*", "ticket.md")
    tickets = glob.glob(pattern)
    if not tickets:
        return None, None
    tickets.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    for path in tickets:
        phase = read_ticket_phase(path)
        if phase:
            return path, phase
    return None, None


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    tool_name = data.get("tool_name", "")
    if tool_name not in RELEVANT_TOOLS:
        sys.exit(0)

    tool_input = data.get("tool_input", {})
    cwd = data.get("cwd", os.getcwd())
    file_path = tool_input.get("file_path", "")

    state = load_state()
    current_head = get_head_hash()
    stored_head = state.get("lastCommitHash", "")

    # --- Commit detection ---
    if current_head and stored_head and current_head != stored_head:
        commit_msg = get_last_commit_message()
        phase = state.get("lastKnownPhase")

        # Clear previous gate on any new commit
        state["gate"] = None
        state["lastCommitHash"] = current_head
        state["locSinceCommit"] = 0

        # Refactor gate: feat: commit during implement phase
        if commit_msg.startswith("feat:") and phase == "implement":
            state["gate"] = "refactor"

    elif not stored_head and current_head:
        # First run — record HEAD without treating as new commit
        state["lastCommitHash"] = current_head

    # --- LOC tracking ---
    loc = get_loc_since_commit()
    state["locSinceCommit"] = loc

    # LOC gate (only if no higher-priority gate is active)
    if not state.get("gate") and loc >= LOC_THRESHOLD:
        state["gate"] = "loc"

    # --- Phase transition detection (ticket.md edits) ---
    if tool_name in EDIT_TOOLS and file_path.endswith("ticket.md"):
        new_phase = read_ticket_phase(file_path)
        old_phase = state.get("lastKnownPhase")
        if new_phase and new_phase != old_phase:
            state["lastKnownPhase"] = new_phase
            state["activeTicket"] = file_path
            # Phase gate overrides LOC gate
            state["gate"] = f"phase:{new_phase}"

    # --- Lazy phase discovery (first run or missing) ---
    if not state.get("lastKnownPhase"):
        ticket_path, phase = find_active_ticket(cwd)
        if ticket_path and phase:
            state["activeTicket"] = ticket_path
            state["lastKnownPhase"] = phase

    state["lastFile"] = file_path
    save_state(state)


if __name__ == "__main__":
    main()
