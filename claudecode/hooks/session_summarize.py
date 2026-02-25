#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Conversation logging for self-improvement (SessionStart/SessionEnd hook).

SessionStart: records session start time and project.
SessionEnd: reads transcript, generates structured summary, persists to
  ~/.claude/session-logs/ and optionally indexes into a knowledge index tool.
"""

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SESSION_LOGS_DIR = Path.home() / ".claude" / "session-logs"
SESSION_STATE_FILE = Path.home() / ".claude" / ".session-state.json"


def handle_start():
    """Record session start metadata."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        data = {}

    state = {
        "start_time": datetime.now(timezone.utc).isoformat(),
        "session_id": data.get("session_id", "unknown"),
        "cwd": data.get("cwd", os.getcwd()),
    }

    SESSION_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    SESSION_STATE_FILE.write_text(json.dumps(state, indent=2))


def handle_end():
    """Generate session summary from transcript."""
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        data = {}

    # Load start state
    try:
        state = json.loads(SESSION_STATE_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        state = {}

    session_id = data.get("session_id", state.get("session_id", "unknown"))
    start_time = state.get("start_time", "")
    project = data.get("cwd", state.get("cwd", "unknown"))
    transcript_path = data.get("transcript_path", "")

    # Parse transcript if available
    prompts = []
    tools_used: set[str] = set()
    files_modified: set[str] = set()

    if transcript_path and os.path.isfile(transcript_path):
        try:
            with open(transcript_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entry = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    # Extract user prompts
                    if entry.get("role") == "user":
                        content = entry.get("content", "")
                        if isinstance(content, str) and content.strip():
                            prompts.append(content.strip()[:200])
                        elif isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "text":
                                    text = block.get("text", "").strip()
                                    if text:
                                        prompts.append(text[:200])

                    # Extract tool usage
                    if entry.get("role") == "assistant":
                        content = entry.get("content", [])
                        if isinstance(content, list):
                            for block in content:
                                if isinstance(block, dict) and block.get("type") == "tool_use":
                                    tool_name = block.get("name", "")
                                    tools_used.add(tool_name)
                                    tool_input = block.get("input", {})
                                    fp = tool_input.get("file_path") or tool_input.get("path", "")
                                    if fp and tool_name in ("Edit", "Write", "MultiEdit", "NotebookEdit"):
                                        files_modified.add(fp)
        except OSError:
            pass

    # Calculate duration
    duration_str = ""
    if start_time:
        try:
            start = datetime.fromisoformat(start_time)
            end = datetime.now(timezone.utc)
            minutes = int((end - start).total_seconds() / 60)
            duration_str = str(minutes)
        except ValueError:
            pass

    # Generate summary markdown
    now = datetime.now(timezone.utc)
    date_str = now.strftime("%Y-%m-%d")
    short_id = session_id[:8] if len(session_id) > 8 else session_id

    lines = [
        "---",
        f"date: {date_str}",
        f"session_id: {session_id}",
        f"project: {project}",
    ]
    if duration_str:
        lines.append(f"duration_minutes: {duration_str}")
    if files_modified:
        lines.append(f"files_modified: {sorted(files_modified)}")
    if tools_used:
        lines.append(f"tools_used: {sorted(tools_used)}")
    lines.extend(["---", ""])

    if prompts:
        lines.append("## Prompts")
        for i, prompt in enumerate(prompts, 1):
            # Truncate long prompts for readability
            display = prompt.replace("\n", " ")[:150]
            lines.append(f"{i}. {display}")
        lines.append("")

    if files_modified:
        lines.append("## Files Modified")
        for fp in sorted(files_modified):
            lines.append(f"- {fp}")
        lines.append("")

    if tools_used:
        lines.append("## Tools Used")
        lines.append(", ".join(sorted(tools_used)))
        lines.append("")

    summary = "\n".join(lines)

    # Write to session logs
    SESSION_LOGS_DIR.mkdir(parents=True, exist_ok=True)
    log_file = SESSION_LOGS_DIR / f"{date_str}-{short_id}.md"
    log_file.write_text(summary)

    # Index into knowledge index tool if configured
    # Set CLAUDE_KNOWLEDGE_INDEX_BIN to the binary name of your knowledge index tool
    knowledge_bin = os.environ.get("CLAUDE_KNOWLEDGE_INDEX_BIN", "")
    if knowledge_bin and shutil.which(knowledge_bin):
        try:
            subprocess.run(
                [knowledge_bin, "add", str(log_file)],
                capture_output=True,
                timeout=30,
            )
        except (subprocess.TimeoutExpired, OSError):
            pass

    # Cleanup state file
    try:
        SESSION_STATE_FILE.unlink()
    except FileNotFoundError:
        pass


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else ""

    if mode == "start":
        handle_start()
    elif mode == "end":
        handle_end()
    else:
        # Default: try to detect from context
        sys.exit(0)


if __name__ == "__main__":
    main()
