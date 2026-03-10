#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

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
            return os.path.expanduser(f"~/.claude/pr-scope-state-{suffix}.json")
    except (subprocess.TimeoutExpired, OSError):
        pass
    return os.path.expanduser("~/.claude/pr-scope-state.json")


STATE_FILE = _state_file()
COMMIT_THRESHOLD = 5
LOC_THRESHOLD = 1000
FILE_THRESHOLD = 15
SUPPRESSION_PROMPTS = 5
BASE_BRANCH_CANDIDATES = ["main", "master"]


def run_git(*args: str) -> str | None:
    try:
        result = subprocess.run(
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode != 0:
            return None
        return result.stdout.strip()
    except (subprocess.TimeoutExpired, OSError):
        return None


def get_base_branch() -> str | None:
    for candidate in BASE_BRANCH_CANDIDATES:
        if run_git("rev-parse", "--verify", candidate) is not None:
            return candidate
    return None


def get_current_branch() -> str | None:
    return run_git("rev-parse", "--abbrev-ref", "HEAD")


def get_metrics(merge_base: str) -> dict:
    commit_count_str = run_git("rev-list", "--count", f"{merge_base}..HEAD")
    commits = int(commit_count_str) if commit_count_str else 0

    numstat = run_git("diff", "--numstat", f"{merge_base}...HEAD")
    loc = 0
    files = 0
    if numstat:
        for line in numstat.splitlines():
            parts = line.split("\t")
            if len(parts) >= 2:
                # Binary files show "-" for additions/deletions — skip them
                try:
                    loc += int(parts[0]) + int(parts[1])
                except ValueError:
                    pass
                files += 1

    return {"commits": commits, "loc": loc, "files": files}


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


def clear_state():
    try:
        os.remove(STATE_FILE)
    except FileNotFoundError:
        pass


def any_threshold_exceeded(metrics: dict) -> bool:
    return (
        metrics["commits"] >= COMMIT_THRESHOLD
        or metrics["loc"] >= LOC_THRESHOLD
        or metrics["files"] >= FILE_THRESHOLD
    )


def scope_increased(current: dict, checkpoint: dict) -> bool:
    return (
        current["commits"] > checkpoint.get("commits", 0)
        or current["loc"] > checkpoint.get("loc", 0)
        or current["files"] > checkpoint.get("files", 0)
    )


def format_warning(metrics: dict) -> str:
    parts = []
    if metrics["commits"] >= COMMIT_THRESHOLD:
        parts.append(f"{metrics['commits']} commits (threshold: {COMMIT_THRESHOLD})")
    if metrics["loc"] >= LOC_THRESHOLD:
        parts.append(f"{metrics['loc']:,} lines changed (threshold: {LOC_THRESHOLD:,})")
    if metrics["files"] >= FILE_THRESHOLD:
        parts.append(f"{metrics['files']} files (threshold: {FILE_THRESHOLD})")
    return f"PR scope check: {', '.join(parts)}. See \"PR Scope Discipline\" in CLAUDE.md."


def format_recheck_warning(current: dict, checkpoint: dict) -> str:
    parts = []
    for key, label, threshold in [
        ("commits", "commits", COMMIT_THRESHOLD),
        ("loc", "lines", LOC_THRESHOLD),
        ("files", "files", FILE_THRESHOLD),
    ]:
        old = checkpoint.get(key, 0)
        new = current[key]
        if new >= threshold:
            delta = new - old
            sign = "+" if delta >= 0 else ""
            parts.append(f"{label} {old:,}→{new:,} ({sign}{delta:,})")
    return (
        f"PR scope re-check: Since last checkpoint — {', '.join(parts)}. "
        f"Scope is growing. See \"PR Scope Discipline\" in CLAUDE.md."
    )


def main():
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        pass

    if run_git("rev-parse", "--git-dir") is None:
        return

    current_branch = get_current_branch()
    base_branch = get_base_branch()
    if current_branch is None or base_branch is None:
        return
    if current_branch == base_branch:
        clear_state()
        return

    merge_base = run_git("merge-base", base_branch, "HEAD")
    if merge_base is None:
        return
    metrics = get_metrics(merge_base)

    if not any_threshold_exceeded(metrics):
        clear_state()
        return

    state = load_state()

    if state.get("branch") != current_branch:
        state = {}

    checkpoint = state.get("checkpoint")

    if checkpoint is None:
        print(format_warning(metrics))
        save_state({
            "branch": current_branch,
            "checkpoint": metrics,
            "prompts_since_warning": 0,
        })
        return

    prompts_since = state.get("prompts_since_warning", 0)

    if prompts_since < SUPPRESSION_PROMPTS:
        state["prompts_since_warning"] = prompts_since + 1
        save_state(state)
        return

    if scope_increased(metrics, checkpoint):
        print(format_recheck_warning(metrics, checkpoint))
        save_state({
            "branch": current_branch,
            "checkpoint": metrics,
            "prompts_since_warning": 0,
        })
    else:
        state["prompts_since_warning"] = 0
        save_state(state)


if __name__ == "__main__":
    main()
