#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Auto-lint files after edits (PostToolUse hook).

Detects file language by extension and runs the appropriate linter/formatter
if installed. Exits silently if the linter is not available.
"""

import json
import os
import shutil
import subprocess
import sys

# Extension → list of (linter_binary, args_template) pairs
# {file} is replaced with the actual file path
LINTERS: dict[str, list[tuple[str, list[str]]]] = {
    ".go": [
        ("golangci-lint", ["run", "--fix", "--issues-exit-code=0", "{file}"]),
    ],
    ".py": [
        ("ruff", ["check", "--fix", "--quiet", "{file}"]),
        ("ruff", ["format", "--quiet", "{file}"]),
    ],
    ".sh": [
        ("shellcheck", ["{file}"]),
    ],
    ".bash": [
        ("shellcheck", ["{file}"]),
    ],
    ".tf": [
        ("tofu", ["fmt", "{file}"]),
        ("terraform", ["fmt", "{file}"]),  # fallback if tofu not installed
    ],
    ".tofu": [
        ("tofu", ["fmt", "{file}"]),
    ],
    ".md": [
        ("markdownlint-cli2", ["--fix", "{file}"]),
    ],
    ".yaml": [
        ("yamllint", ["-d", "relaxed", "{file}"]),
    ],
    ".yml": [
        ("yamllint", ["-d", "relaxed", "{file}"]),
    ],
}


def get_file_path(data: dict) -> str | None:
    tool_input = data.get("tool_input", {})
    return tool_input.get("file_path") or tool_input.get("path")


def run_linter(binary: str, args: list[str], file_path: str) -> bool:
    if not shutil.which(binary):
        return False

    resolved_args = [a.replace("{file}", file_path) for a in args]
    try:
        subprocess.run(
            [binary, *resolved_args],
            capture_output=True,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, OSError):
        pass
    return True


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    file_path = get_file_path(data)
    if not file_path or not os.path.isfile(file_path):
        sys.exit(0)

    ext = os.path.splitext(file_path)[1].lower()
    linters = LINTERS.get(ext, [])

    for binary, args in linters:
        if run_linter(binary, args, file_path):
            break  # Use first available linter for this extension


if __name__ == "__main__":
    main()
