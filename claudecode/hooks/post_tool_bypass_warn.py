#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Detect quality bypass patterns in edited files (PostToolUse hook).

Scans file content after edits for lint suppressions, skipped tests,
swallowed errors, and other bypass patterns. Requires approval if found.
"""

import json
import os
import re
import sys

# Patterns that require approval — (regex, description, file extensions or None for all)
BYPASS_PATTERNS: list[tuple[str, str, set[str] | None]] = [
    # Go
    (r"//nolint", "Go lint suppression (//nolint)", {".go"}),
    (r"_\s*=\s*err\b", "Swallowed Go error (_ = err)", {".go"}),
    (r"t\.Skip\(", "Skipped Go test (t.Skip)", {".go", "_test.go"}),
    # Python
    (r"#\s*noqa", "Python lint suppression (# noqa)", {".py"}),
    (r"#\s*type:\s*ignore", "Python type suppression (# type: ignore)", {".py"}),
    (r"@pytest\.mark\.skip", "Skipped Python test (@pytest.mark.skip)", {".py"}),
    (r"pytest\.skip\(", "Skipped Python test (pytest.skip())", {".py"}),
    # Terraform / OpenTofu
    (
        r"lifecycle\s*\{[^}]*ignore_changes",
        "Terraform lifecycle ignore_changes",
        {".tf", ".tofu"},
    ),
    # General
    (r"eslint-disable", "ESLint suppression", {".js", ".ts", ".jsx", ".tsx"}),
    (r"@ts-ignore", "TypeScript suppression (@ts-ignore)", {".ts", ".tsx"}),
    (r"@ts-expect-error", "TypeScript suppression (@ts-expect-error)", {".ts", ".tsx"}),
]


def get_file_path(data: dict) -> str | None:
    tool_input = data.get("tool_input", {})
    return tool_input.get("file_path") or tool_input.get("path")


def check_file(file_path: str) -> list[str]:
    if not os.path.isfile(file_path):
        return []

    ext = os.path.splitext(file_path)[1]
    findings = []

    try:
        with open(file_path, encoding="utf-8", errors="replace") as f:
            content = f.read()
    except OSError:
        return []

    for pattern, description, extensions in BYPASS_PATTERNS:
        if extensions and ext not in extensions:
            continue
        if re.search(pattern, content):
            findings.append(description)

    return findings


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    file_path = get_file_path(data)
    if not file_path:
        sys.exit(0)

    findings = check_file(file_path)
    if not findings:
        sys.exit(0)

    finding_list = ", ".join(findings)
    print(
        f"Quality bypass detected in {os.path.basename(file_path)}: {finding_list}. "
        "Ensure this is intentional and document the reason.",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
