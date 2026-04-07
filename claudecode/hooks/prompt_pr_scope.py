#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///

import json
import os
import subprocess
import sys

COMMIT_THRESHOLD = 10
LOC_THRESHOLD = 1000
FILE_THRESHOLD = 15
SUPPRESS_SKIP_COUNT = 5
BASE_BRANCH_CANDIDATES = ["main", "master"]


def get_state_file(repo_root: str, branch: str) -> str:
    import hashlib
    repo_hash = hashlib.sha1(repo_root.encode()).hexdigest()[:8]
    safe_branch = branch.replace("/", "--")
    return os.path.expanduser(f"~/.claude/pr-scope-state-{repo_hash}-{safe_branch}.json")


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
    # Prefer remote-tracking refs — they reflect the actual PR target
    # and don't go stale when the local branch isn't updated.
    # Check ALL remote refs before ANY local ref to avoid a stale local
    # "main" shadowing a valid "origin/master" (or vice versa).
    refs = [f"origin/{c}" for c in BASE_BRANCH_CANDIDATES] + list(BASE_BRANCH_CANDIDATES)
    for ref in refs:
        if run_git("rev-parse", "--verify", ref) is not None:
            return ref
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


def load_state(state_file: str) -> dict:
    try:
        with open(state_file) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def save_state(state: dict, state_file: str):
    os.makedirs(os.path.dirname(state_file), exist_ok=True)
    with open(state_file, "w") as f:
        json.dump(state, f, indent=2)


def clear_state(state_file: str):
    try:
        os.remove(state_file)
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
    for key, label, _ in [
        ("commits", "commits", COMMIT_THRESHOLD),
        ("loc", "lines", LOC_THRESHOLD),
        ("files", "files", FILE_THRESHOLD),
    ]:
        old = checkpoint.get(key, 0)
        new = current[key]
        if new > old:
            delta = new - old
            sign = "+"
            parts.append(f"{label} {old:,}->{new:,} ({sign}{delta:,})")
    return (
        f"PR scope re-check: Since last checkpoint -- {', '.join(parts)}. "
        f"Scope is growing. See \"PR Scope Discipline\" in CLAUDE.md."
    )


def main():
    try:
        json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        pass

    repo_root = run_git("rev-parse", "--show-toplevel")
    if repo_root is None:
        return

    current_branch = get_current_branch()
    base_branch = get_base_branch()
    if current_branch is None or base_branch is None:
        return

    state_file = get_state_file(repo_root, current_branch)

    if current_branch in BASE_BRANCH_CANDIDATES:
        clear_state(state_file)
        return

    merge_base = run_git("merge-base", base_branch, "HEAD")
    if merge_base is None:
        return
    metrics = get_metrics(merge_base)

    if not any_threshold_exceeded(metrics):
        clear_state(state_file)
        return

    state = load_state(state_file)
    checkpoint = state.get("checkpoint")

    if checkpoint is None:
        print(format_warning(metrics))
        save_state({
            "checkpoint": metrics,
            "prompts_since_warning": 0,
        }, state_file)
        return

    prompts_since = state.get("prompts_since_warning", 0)

    if prompts_since < SUPPRESS_SKIP_COUNT:
        state["prompts_since_warning"] = prompts_since + 1
        save_state(state, state_file)
        return

    if scope_increased(metrics, checkpoint):
        print(format_recheck_warning(metrics, checkpoint))
        save_state({
            "checkpoint": metrics,
            "prompts_since_warning": 0,
        }, state_file)
    else:
        state["prompts_since_warning"] = 0
        save_state(state, state_file)


if __name__ == "__main__":
    main()
