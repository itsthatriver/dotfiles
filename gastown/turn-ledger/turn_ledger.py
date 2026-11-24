#!/usr/bin/env python3
"""Per-turn token ledger for Gas Town agents.

Registered as a Claude Code hook (Stop, SessionStart, SessionEnd), it appends
one JSON line per completed turn, with exact token counts and a rules-based
goal label, to <ledger home>/YYYY-MM-DD.jsonl (UTC date of the turn's end).

    turn_ledger.py hook [--agent claude|codex]   hook JSON on stdin
    turn_ledger.py install-hooks [hooks-base.json]
    turn_ledger.py install-codex-hooks [hooks.json]

One invocation is not one turn: a hook can fire while the transcript lags, or
after several turns have piled up. Each run reads from a per-session cursor,
closes every turn that is provably finished, and moves the cursor to the first
turn still open.

The hook never breaks the agent: any failure is appended to errors.log with
full context and the process exits 0.
"""

from __future__ import annotations

import json
import os
import re
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import goals

# ---------------------------------------------------------------------------
# Shared: paths, pricing, identity, ledger output
# ---------------------------------------------------------------------------

TOKEN_KEYS = ("input", "output", "cache_write_5m", "cache_write_1h", "cache_read")

# $ per million tokens, in TOKEN_KEYS order. From the token analysis of
# 2026-11-24 (claude-api skill model table); cache writes are 1.25x / 2x input.
PRICES = {
    "claude-opus-5-5": (4.00, 20.00, 5.00, 8.00, 0.20),
    "claude-sonnet-5-5": (2.00, 10.00, 2.50, 4.00, 0.10),
    "claude-sonnet-5": (2.00, 10.00, 2.50, 4.00, 0.20),
    "claude-fable-5-1": (10.00, 50.00, 12.50, 20.00, 1.00),
    "claude-haiku-5-5": (0.10, 0.50, 0.125, 0.20, 0.01),
    "claude-haiku-4-5-20251001": (1.00, 5.00, 1.25, 2.00, 0.10),
}

PROMPT_HEAD_CHARS = 80
SAFE_SESSION_ID = re.compile(r"^[A-Za-z0-9._-]+$")


def ledger_home() -> Path:
    default = Path.home() / "gt/.runtime/turn-ledger"
    return Path(os.environ.get("TURN_LEDGER_HOME", default))


def town_root() -> Path:
    return Path(os.environ.get("TURN_LEDGER_TOWN", Path.home() / "gt"))


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_ts(text: str) -> datetime:
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def empty_tokens() -> dict:
    return {key: 0 for key in TOKEN_KEYS}


def add_tokens(models: dict, model: str, tokens: dict) -> None:
    total = models.setdefault(model, empty_tokens())
    for key in TOKEN_KEYS:
        total[key] += tokens[key]


def cost_of(models: dict) -> float:
    """Dollar equivalent of per-model tokens; models without a price count 0."""
    usd = 0.0
    for model, tokens in models.items():
        prices = PRICES.get(model)
        if prices:
            usd += (
                sum(tokens[key] * price for key, price in zip(TOKEN_KEYS, prices)) / 1e6
            )
    return usd


def unpriced_models(*model_dicts: dict) -> list:
    names = set()
    for models in model_dicts:
        for model, tokens in models.items():
            if model not in PRICES and any(tokens.values()):
                names.add(model)
    return sorted(names)


def identify(cwd: str) -> tuple:
    """Return (role, rig, name) for an agent's working directory."""
    try:
        parts = Path(cwd).relative_to(town_root()).parts
    except ValueError:
        return "other", None, None
    if not parts:
        return "other", None, None
    if parts[0] == "mayor":
        return "mayor", "town", "mayor"
    if parts[0] == "deacon":
        if len(parts) >= 3 and parts[1] == "dogs":
            return ("boot" if parts[2] == "boot" else "dog"), "town", parts[2]
        return "deacon", "town", "deacon"
    if len(parts) >= 2 and parts[1] in ("crew", "polecats"):
        role = "crew" if parts[1] == "crew" else "polecat"
        return role, parts[0], parts[2] if len(parts) > 2 else None
    if len(parts) >= 2 and parts[1] in ("witness", "refinery"):
        return parts[1], parts[0], parts[1]
    return "other", None, None


def log_error(home: Path, event: str, session_id: str, detail: str) -> None:
    """Append one failure, with enough context to debug it, to errors.log."""
    home.mkdir(parents=True, exist_ok=True)
    entry = f"{now_iso()} event={event} session_id={session_id}\n{detail.rstrip()}\n\n"
    with (home / "errors.log").open("a") as handle:
        handle.write(entry)


def append_records(home: Path, records: list) -> None:
    """Append records to their UTC-date files, one write per file."""
    by_date: dict = {}
    for record in records:
        date = parse_ts(record["ts_end"]).astimezone(timezone.utc).date().isoformat()
        by_date.setdefault(date, []).append(record)
    home.mkdir(parents=True, exist_ok=True)
    for date, day_records in by_date.items():
        payload = "".join(
            json.dumps(r, separators=(",", ":")) + "\n" for r in day_records
        ).encode()
        descriptor = os.open(
            home / f"{date}.jsonl", os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600
        )
        try:
            written = 0
            while written < len(payload):
                written += os.write(descriptor, payload[written:])
        finally:
            os.close(descriptor)


# ---------------------------------------------------------------------------
# Shared: per-session cursor
# ---------------------------------------------------------------------------


def cursor_path(home: Path, session_id: str) -> Path:
    if not SAFE_SESSION_ID.match(session_id):
        raise ValueError(f"unsafe session_id {session_id!r}")
    return home / "cursors" / f"{session_id}.json"


def load_cursor(home: Path, session_id: str, transcript: Path) -> dict:
    """Return the saved cursor, or a fresh one when the transcript changed."""
    path = cursor_path(home, session_id)
    fresh = {"transcript_path": str(transcript), "offset": 0}
    if not path.exists():
        return fresh
    cursor = json.loads(path.read_text())
    if cursor.get("transcript_path") != str(transcript):
        return fresh
    if transcript.stat().st_size < cursor["offset"]:
        log_error(
            home,
            "cursor",
            session_id,
            f"transcript {transcript} is smaller than its cursor ({cursor['offset']}); restarting from the top",
        )
        return fresh
    return cursor


def save_cursor(home: Path, session_id: str, cursor: dict) -> None:
    path = cursor_path(home, session_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temp_name = tempfile.mkstemp(dir=path.parent, prefix=".cursor-")
    with os.fdopen(descriptor, "w") as handle:
        json.dump(cursor, handle)
    os.replace(temp_name, path)


@dataclass
class TurnFacts:
    """Everything the ledger knows about one finished turn, agent-neutral."""

    agent: str
    session_id: str
    cwd: str
    prompt: str
    prompt_id: str | None
    prompt_kind: str
    flags: str
    ts_start: str
    ts_end: str
    models: dict
    api_calls: int
    cold_calls: int
    ctx_max: int
    tool_sig: dict
    tokens_by_signature: dict
    subagent_models: dict = field(default_factory=dict)
    subagent_api_calls: int = 0


ISSUE_REF = re.compile(r"\b[A-Z]{2,6}-\d+\b|(?<![\w&])#\d{1,6}\b")
NOT_ISSUE_PREFIXES = ("UTF-", "SHA-", "ISO-", "RFC-", "CVE-", "TLS-", "AES-", "GPT-")
MAX_ISSUE_REFS = 20


def issue_refs(prompt: str) -> list:
    refs: list = []
    for match in ISSUE_REF.findall(prompt):
        if match.startswith(NOT_ISSUE_PREFIXES) or match in refs:
            continue
        refs.append(match)
    return refs[:MAX_ISSUE_REFS]


def build_record(facts: TurnFacts) -> dict:
    role, rig, name = identify(facts.cwd)
    goal, rule, confidence, subtype = goals.classify(
        facts.prompt, facts.tokens_by_signature, facts.flags
    )
    subagent_usd = cost_of(facts.subagent_models)
    return {
        "agent": facts.agent,
        "session_id": facts.session_id,
        "prompt_id": facts.prompt_id,
        "role": role,
        "rig": rig,
        "name": name,
        "ts_start": facts.ts_start,
        "ts_end": facts.ts_end,
        "models": facts.models,
        "usd_equiv": round(cost_of(facts.models) + subagent_usd, 6),
        "api_calls": facts.api_calls,
        "cold_calls": facts.cold_calls,
        "ctx_max": facts.ctx_max,
        "subagent_usd": round(subagent_usd, 6),
        "subagent_models": facts.subagent_models,
        "subagent_api_calls": facts.subagent_api_calls,
        "prompt_kind": facts.prompt_kind,
        "subtype": subtype,
        "tool_sig": facts.tool_sig,
        "issue_refs": issue_refs(facts.prompt),
        "goal": goal,
        "goal_rule": rule,
        "goal_conf": confidence,
        "unpriced_models": unpriced_models(facts.models, facts.subagent_models),
        "prompt_head": " ".join(facts.prompt.split())[:PROMPT_HEAD_CHARS],
    }


# ---------------------------------------------------------------------------
# Claude Code transcripts
# ---------------------------------------------------------------------------

USAGE_FIELDS = (
    "input_tokens",
    "output_tokens",
    "cache_creation_input_tokens",
    "cache_read_input_tokens",
)
CACHE_CREATION_FIELDS = ("ephemeral_5m_input_tokens", "ephemeral_1h_input_tokens")
OPEN_STOP_REASONS = (None, "tool_use")


def text_of(content) -> str:
    if isinstance(content, str):
        return content
    return "\n".join(
        block.get("text", "")
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    )


def is_turn_start(record: dict) -> bool:
    """A real prompt: user text, not a tool_result handing output back."""
    if record.get("type") != "user" or record.get("isSidechain"):
        return False
    content = (record.get("message") or {}).get("content")
    if isinstance(content, str):
        return True
    return isinstance(content, list) and not any(
        isinstance(block, dict) and block.get("type") == "tool_result"
        for block in content
    )


def tool_label(block: dict) -> tuple:
    """Return (label, argument head) for a tool_use block."""
    name, tool_input = block.get("name", "?"), block.get("input") or {}
    if name == "Bash":
        return name, (tool_input.get("command") or "")[:200]
    if name.endswith("Arcade_UseTool"):
        return "Arcade:" + str(tool_input.get("tool_name")), json.dumps(
            tool_input.get("inputs", {})
        )[:120]
    if name == "Agent":
        return name, (tool_input.get("description") or tool_input.get("prompt") or "")[
            :160
        ]
    if name == "Skill":
        return "Skill:" + str(tool_input.get("skill")), ""
    if name in ("Edit", "Write", "Read", "NotebookEdit"):
        return name, str(tool_input.get("file_path", ""))[-80:]
    return name, ""


@dataclass
class Message:
    """One API response. Streaming writes it as several records; fields take the max."""

    message_id: str
    model: str
    first_ts: str
    last_ts: str
    usage: dict
    cache_creation: dict | None = None
    stop_reason: str | None = None
    tools: dict = field(default_factory=dict)

    def absorb(self, record: dict) -> None:
        message = record["message"]
        usage = message["usage"]
        for name in USAGE_FIELDS:
            self.usage[name] = max(self.usage[name], usage.get(name) or 0)
        breakdown = usage.get("cache_creation")
        if isinstance(breakdown, dict):
            if self.cache_creation is None:
                self.cache_creation = {name: 0 for name in CACHE_CREATION_FIELDS}
            for name in CACHE_CREATION_FIELDS:
                self.cache_creation[name] = max(
                    self.cache_creation[name], breakdown.get(name) or 0
                )
        timestamp = record.get("timestamp") or self.last_ts
        self.last_ts = max(self.last_ts, timestamp)
        self.stop_reason = message.get("stop_reason")
        for block in message.get("content") or []:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                self.tools.setdefault(
                    block.get("id") or len(self.tools), tool_label(block)
                )

    def tokens(self) -> dict:
        if self.cache_creation is not None:
            cache_write_5m = self.cache_creation["ephemeral_5m_input_tokens"]
            cache_write_1h = self.cache_creation["ephemeral_1h_input_tokens"]
        else:
            cache_write_5m, cache_write_1h = (
                self.usage["cache_creation_input_tokens"],
                0,
            )
        return {
            "input": self.usage["input_tokens"],
            "output": self.usage["output_tokens"],
            "cache_write_5m": cache_write_5m,
            "cache_write_1h": cache_write_1h,
            "cache_read": self.usage["cache_read_input_tokens"],
        }

    def context_size(self) -> int:
        return (
            self.usage["input_tokens"]
            + self.usage["cache_creation_input_tokens"]
            + self.usage["cache_read_input_tokens"]
        )

    def signatures(self) -> list:
        return [
            goals.signature(label, argument) for label, argument in self.tools.values()
        ]


def merge_messages(records: list) -> list:
    """Dedupe assistant records by message id, in order of first appearance."""
    messages: dict = {}
    for record in records:
        message = record.get("message") or {}
        if not message.get("usage"):
            continue
        message_id = message.get("id") or record.get("requestId") or record.get("uuid")
        timestamp = record.get("timestamp") or ""
        if message_id not in messages:
            messages[message_id] = Message(
                message_id,
                message.get("model") or "?",
                timestamp,
                timestamp,
                {name: 0 for name in USAGE_FIELDS},
            )
        messages[message_id].absorb(record)
    return list(messages.values())


@dataclass
class ClaudeTurn:
    start_offset: int
    ts_start: str
    prompt: str = ""
    prompt_id: str | None = None
    flags: str = ""
    origin: str | None = None
    assistant_records: list = field(default_factory=list)

    def is_finished(self) -> bool:
        """The last assistant message ended the turn rather than calling a tool."""
        messages = merge_messages(self.assistant_records)
        return bool(messages) and messages[-1].stop_reason not in OPEN_STOP_REASONS

    def prompt_kind(self) -> str:
        if "isCompactSummary" in self.flags:
            return "compact_summary"
        if not self.prompt:
            return "none"
        return self.origin or "unknown"


def read_json_lines(path: Path, offset: int, wanted: tuple) -> tuple:
    """Return (lines, end, corrupt) for the complete JSON lines from offset.

    lines is a list of (start, end, record); end is the offset just past the
    last complete line. A final line without a newline counts only if it
    parses; otherwise it is still being written and is left for the next run.
    corrupt lists (offset, error) for complete lines that are not JSON. Lines
    that cannot hold a wanted marker are skipped without parsing.
    """
    lines: list = []
    corrupt: list = []
    with path.open("rb") as handle:
        handle.seek(offset)
        position = offset
        for raw in handle:
            start = position
            complete = raw.endswith(b"\n")
            if complete and not any(marker in raw for marker in wanted):
                position += len(raw)
                continue
            try:
                record = json.loads(raw)
            except ValueError as error:
                if not complete:
                    break
                corrupt.append((start, error))
            else:
                lines.append((start, start + len(raw), record))
            position += len(raw)
    return lines, position, corrupt


def read_claude_turns(path: Path, offset: int) -> tuple:
    """Return (turns, end offset of the last complete line, corrupt lines)."""
    lines, end, corrupt = read_json_lines(path, offset, (b'"assistant"', b'"user"'))
    turns: list = []
    for start, _, record in lines:
        timestamp = record.get("timestamp") or ""
        if is_turn_start(record):
            flags = " ".join(
                key for key in ("isMeta", "isCompactSummary") if record.get(key)
            )
            turns.append(
                ClaudeTurn(
                    start,
                    timestamp,
                    text_of(record["message"]["content"]),
                    record.get("promptId"),
                    flags,
                    (record.get("origin") or {}).get("kind"),
                )
            )
        elif record.get("type") == "assistant" and not record.get("isSidechain"):
            if not turns:
                turns.append(ClaudeTurn(start, timestamp))
            turns[-1].assistant_records.append(record)
    return turns, end, corrupt


def summarize_claude_turn(turn: ClaudeTurn, session_id: str, cwd: str) -> TurnFacts:
    messages = merge_messages(turn.assistant_records)
    models: dict = {}
    tool_sig: dict = {}
    tokens_by_signature: dict = {}
    for message in messages:
        tokens = message.tokens()
        add_tokens(models, message.model, tokens)
        signatures = message.signatures()
        for signature in signatures:
            tool_sig[signature] = tool_sig.get(signature, 0) + 1
        total = sum(tokens.values())
        for signature in signatures or ["text"]:
            tokens_by_signature[signature] = tokens_by_signature.get(
                signature, 0
            ) + total / len(signatures or [1])
    return TurnFacts(
        agent="claude",
        session_id=session_id,
        cwd=cwd,
        prompt=turn.prompt,
        prompt_id=turn.prompt_id,
        prompt_kind=turn.prompt_kind(),
        flags=turn.flags,
        ts_start=turn.ts_start or (messages[0].first_ts if messages else ""),
        ts_end=max([m.last_ts for m in messages], default=turn.ts_start),
        models=models,
        api_calls=len(messages),
        cold_calls=0,
        ctx_max=max([m.context_size() for m in messages], default=0),
        tool_sig=tool_sig,
        tokens_by_signature=tokens_by_signature,
    )


def ingest_claude(home: Path, event: dict) -> int:
    """Close every finished turn since the cursor; return how many were written."""
    session_id = event["session_id"]
    transcript = Path(event["transcript_path"])
    flush = event.get("hook_event_name") == "SessionEnd"
    if not transcript.exists():
        if event.get("hook_event_name") == "SessionStart":
            return 0
        raise FileNotFoundError(f"transcript {transcript} does not exist")
    cursor = load_cursor(home, session_id, transcript)
    turns, end, corrupt = read_claude_turns(transcript, cursor["offset"])
    for offset, error in corrupt:
        log_error(
            home,
            event.get("hook_event_name", "?"),
            session_id,
            f"skipped corrupt line at byte {offset}: {error}",
        )
    open_turn = None
    if turns and not flush and not turns[-1].is_finished():
        open_turn = turns.pop()
    records = [
        build_record(summarize_claude_turn(turn, session_id, event.get("cwd") or ""))
        for turn in turns
    ]
    append_records(home, records)
    cursor["offset"] = open_turn.start_offset if open_turn else end
    save_cursor(home, session_id, cursor)
    return len(records)


def ingest(home: Path, agent: str, event: dict) -> int:
    if agent == "claude":
        return ingest_claude(home, event)
    raise ValueError(f"unknown agent {agent!r}")
