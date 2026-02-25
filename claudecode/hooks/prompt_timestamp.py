#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""Inject current timestamp into Claude's context (UserPromptSubmit hook)."""

from datetime import datetime, timezone

now = datetime.now(timezone.utc)
local = datetime.now().astimezone()

natural = now.strftime("%A, %B %d, %Y %I:%M %p UTC")
iso = now.isoformat()
local_str = local.strftime("%I:%M %p %Z")

print(f"Current time: {natural} ({iso}) | Local: {local_str}")
