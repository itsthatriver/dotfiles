#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Phase-aware quality review and done-phase enforcement (Stop hook).

Phase == 'done': Searches transcript for evidence and blocks stop (exit 2)
                 until test results, scenario completion, and audit are found.
All other phases: Prints phase-specific review questions.
No phase tracked: Prints generic quality reminder.
"""

import hashlib
import json
import os
import re
import subprocess
import sys

PHASE_REVIEWS = {
    "intake": (
        "Discovery review:\n"
        "- Is the goal clearly defined?\n"
        "- Is scope documented (in/out)?\n"
        "- Were failure modes explored?\n"
        "- Are there remaining unknowns that need discovery rounds?"
    ),
    "define-behavior": (
        "Scenario review:\n"
        "- Do scenarios cover happy path, failure modes, AND edge cases?\n"
        "- Is each scenario Atomic, Observable, Deterministic?\n"
        "- Are Given/When/Then clauses specific enough to implement?"
    ),
    "scenario-gate": (
        "Scenario validation review:\n"
        "- Did each scenario pass the AOD quality gate?\n"
        "- Were issues reported and resolved?\n"
        "- Are scenarios saved to test-definitions.md?"
    ),
    "decomposition": (
        "Decomposition review:\n"
        "- Are components identified with test layers assigned?\n"
        "- Is the task order dependency-correct (bottom-up)?\n"
        "- Is each task small enough for one TDD cycle?"
    ),
    "implement": (
        "Implementation review:\n"
        "- Did you follow RED \u2192 GREEN \u2192 REFACTOR for each scenario?\n"
        "- Is each scenario marked [x] in test-definitions.md?\n"
        "- Are commits following convention (test:/feat:/refactor:)?\n"
        "- Did you run the full test suite after each GREEN?"
    ),
}

# Evidence patterns the /done command produces (case-insensitive)
EVIDENCE_TESTS = re.compile(r"\d+/\d+\s*tests?\s*pass", re.IGNORECASE)
EVIDENCE_SCENARIOS = re.compile(
    r"all\s+\d+\s+scenarios?\s+(marked\s+)?complete", re.IGNORECASE
)
EVIDENCE_AUDIT = re.compile(r"audit\s+(passed|clean)", re.IGNORECASE)


def _state_file() -> str:
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


def load_state() -> dict:
    try:
        with open(_state_file()) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def read_ticket_phase(file_path: str) -> str | None:
    """Re-read phase from ticket to guard against stale state."""
    if not file_path or not os.path.exists(file_path):
        return None
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


def read_transcript_text(transcript_path: str, max_lines: int = 200) -> str:
    """Extract text from the tail of the transcript JSONL."""
    try:
        with open(transcript_path) as f:
            lines = f.readlines()
    except (FileNotFoundError, OSError):
        return ""

    tail = lines[-max_lines:] if len(lines) > max_lines else lines
    parts = []
    for line in tail:
        try:
            entry = json.loads(line)
            msg = entry.get("message", {})
            role = msg.get("role", "")
            # Assistant messages contain response text and tool results
            if role == "assistant":
                for block in msg.get("content", []):
                    if isinstance(block, dict) and block.get("type") == "text":
                        parts.append(block["text"])
            # Tool results returned to the assistant
            elif entry.get("type") == "tool_result":
                content = entry.get("content", "")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for item in content:
                        if isinstance(item, dict) and item.get("type") == "text":
                            parts.append(item["text"])
        except (json.JSONDecodeError, KeyError, TypeError, AttributeError):
            continue
    return "\n".join(parts)


def check_done_evidence(text: str, is_feature: bool) -> list[str]:
    """Return list of missing evidence for done phase."""
    missing = []
    if not EVIDENCE_TESTS.search(text):
        missing.append("Test results (e.g., '15/15 tests pass')")
    if is_feature:
        if not EVIDENCE_SCENARIOS.search(text):
            missing.append("Scenario completion (e.g., 'All 5 scenarios complete')")
        if not EVIDENCE_AUDIT.search(text):
            missing.append("Audit results (run /audit)")
    return missing


def is_feature_ticket(state: dict) -> bool:
    """Check if active ticket has test-definitions.md (feature-level work)."""
    ticket_path = state.get("activeTicket", "")
    if not ticket_path:
        return False
    ticket_dir = os.path.dirname(ticket_path)
    return os.path.exists(os.path.join(ticket_dir, "test-definitions.md"))


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    transcript_path = data.get("transcript_path", "")
    state = load_state()
    phase = state.get("lastKnownPhase")

    # --- No phase tracked — generic review ---
    if not phase:
        print(
            "Quality check: Before finishing, verify \u2014\n"
            "(1) Do changes follow the methodology (patch/task/feature)?\n"
            "(2) Are there tests for new behavior?\n"
            "(3) Is there unreferenced code to clean up?\n"
            "(4) Are commit messages descriptive enough for agent handoff?"
        )
        sys.exit(0)

    # --- Done phase — hard block with evidence check ---
    if phase == "done":
        # Verify phase is still current (guard against stale state)
        actual_phase = read_ticket_phase(state.get("activeTicket", ""))
        if actual_phase != "done":
            print(
                f"Quality check: Phase state was stale (expected 'done', "
                f"found '{actual_phase}'). Clearing."
            )
            sys.exit(0)

        if not transcript_path:
            print(
                "Done phase active but no transcript available. "
                "Run /done to complete the checklist.",
                file=sys.stderr,
            )
            sys.exit(2)

        transcript_text = read_transcript_text(transcript_path)
        is_feature = is_feature_ticket(state)
        missing = check_done_evidence(transcript_text, is_feature)

        if missing:
            msg = (
                "DONE PHASE \u2014 cannot stop without evidence.\n\n"
                "Missing:\n"
                + "\n".join(f"  - {m}" for m in missing)
                + "\n\nRun /done to produce the required evidence."
            )
            print(msg, file=sys.stderr)
            sys.exit(2)

        print("Done phase complete. All evidence verified.")
        sys.exit(0)

    # --- Phase-specific review ---
    review = PHASE_REVIEWS.get(phase)
    if review:
        print(review)
    else:
        print(
            f"Quality check (phase: {phase}):\n"
            "- Are changes aligned with this phase's goals?\n"
            "- Is it time to transition to the next phase?"
        )


if __name__ == "__main__":
    main()
