#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Remind Claude to research before asking questions (UserPromptSubmit hook)."""

print(
    "Research before asking. Debate options internally "
    "(correct? elegant? latest practices? simplest path?), "
    "then ask 1-5 targeted questions about scope, constraints, "
    "or success criteria."
)
