#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Guard quality-critical config files from modification (PreToolUse hook).

Reads tool_input from stdin, checks file path against protected patterns.
Outputs permissionDecision: "ask" if the file is a protected config.
"""

import json
import re
import sys

EDIT_TOOLS = {"Edit", "Write", "MultiEdit", "NotebookEdit"}

PROTECTED_PATTERNS = [
    # Go
    r"(^|/)go\.(mod|sum)$",
    r"(^|/)\.golangci\.(yml|yaml|toml|json)$",
    # Python
    r"(^|/)pyproject\.toml$",
    r"(^|/)setup\.(py|cfg)$",
    r"(^|/)ruff\.toml$",
    r"(^|/)\.ruff\.toml$",
    r"(^|/)mypy\.ini$",
    r"(^|/)\.flake8$",
    r"(^|/)\.python-version$",
    r"(^|/)uv\.lock$",
    # Terraform / OpenTofu
    r"(^|/)\.terraform\.lock\.hcl$",
    r"(^|/)backend\.tf$",
    r"(^|/)providers\.tf$",
    r"(^|/)versions\.tf$",
    # Pulumi
    r"(^|/)Pulumi\.(yaml|yml)$",
    r"(^|/)Pulumi\..+\.(yaml|yml)$",
    # CI/CD
    r"(^|/)\.github/workflows/.+\.(yml|yaml)$",
    r"(^|/)\.gitlab-ci\.(yml|yaml)$",
    r"(^|/)Jenkinsfile$",
    r"(^|/)Makefile$",
    # Linting / Formatting
    r"(^|/)\.?eslint",
    r"(^|/)\.?prettier",
    r"(^|/)tsconfig.*\.json$",
    r"(^|/)\.editorconfig$",
    r"(^|/)\.markdownlint",
    # Docker
    r"(^|/)Dockerfile",
    r"(^|/)docker-compose\.(yml|yaml)$",
    r"(^|/)compose\.(yml|yaml)$",
]


def get_file_path(data: dict) -> str | None:
    tool_input = data.get("tool_input", {})
    return tool_input.get("file_path") or tool_input.get("path")


def main():
    try:
        data = json.load(sys.stdin)
    except (json.JSONDecodeError, EOFError):
        sys.exit(0)

    if data.get("tool_name") not in EDIT_TOOLS:
        sys.exit(0)

    file_path = get_file_path(data)
    if not file_path:
        sys.exit(0)

    for pattern in PROTECTED_PATTERNS:
        if re.search(pattern, file_path):
            basename = file_path.rsplit("/", 1)[-1] if "/" in file_path else file_path
            result = {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "ask",
                    "permissionDecisionReason": (
                        f"Modifying config file '{basename}' — "
                        "this affects project-wide quality settings."
                    ),
                }
            }
            json.dump(result, sys.stdout)
            sys.exit(0)


if __name__ == "__main__":
    main()
