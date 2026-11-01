#!/usr/bin/env python3
"""Turn what needs River in Slack into issues on Linear team RIV.

Only an LLM session can read Slack through the Arcade gateway and judge what
needs River, so the slack-triage dog does that. This script owns everything
else: the time window each run covers, which Slack threads already have an
issue, the exact Linear calls to make, the run lease, and escalation.

    slack_triage.py begin           Takes the run lease and prints the window
                                    to read: WINDOW <start> <end>. Prints BUSY
                                    if another run holds the lease.
    slack_triage.py plan            Reads the dog's items (JSON on stdin) and
                                    prints DONE <summary>, or CALLS <n> then one
                                    "CALL <id> <json>" line per Linear call.
    slack_triage.py apply [reason]  Reads pending/<id>.json for each call the
                                    dog made, records the issues, and advances
                                    the window. A reason says which call failed.
    slack_triage.py fail <reason>   Records a failed run and releases the lease;
                                    escalates on the 5th failure in a row.

Delivery is off until the file DELIVER exists in the runtime directory; until
then plan appends every Linear call it would make to dry-run.log, makes none,
and advances the window without recording any issue.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RUNTIME_DIR = Path(
    os.environ.get("SLACK_TRIAGE_HOME", Path.home() / "gt/.runtime/slack-triage")
)
STATE_FILE = RUNTIME_DIR / "state.json"
PENDING_DIR = RUNTIME_DIR / "pending"
PLAN_FILE = PENDING_DIR / "plan.json"
DRY_RUN_LOG = RUNTIME_DIR / "dry-run.log"
DELIVER_FLAG = RUNTIME_DIR / "DELIVER"
RUN_LEASE = RUNTIME_DIR / "run.lease"
LOCK_FILE = RUNTIME_DIR / "slack-triage.lock"
GT = os.environ.get("SLACK_TRIAGE_GT", "gt")

# @web stopped at 4:05 PM PT on 10-29; the first window starts there.
FIRST_WINDOW_START = "2026-10-29T23:05:00Z"
# A long outage would otherwise hand one dog days of Slack to read.
MAX_WINDOW = timedelta(hours=12)
RUN_LEASE_TTL = timedelta(minutes=20)
ESCALATE_AFTER_FAILURES = 5

TEAM = "RIV"
TODO_STATE = "Todo"
NEEDS_RIVER_LABEL_ID = "66b00900-266c-4e29-986a-8498b980185b"
# River's replies on agent:phagey issues reach phagey through riv-relay.
AGENT_LABEL_ID = "8360f084-000f-4827-8ffa-49b1cbaebada"
SLACK_LABEL_ID = "ff6aa6d3-cfa0-4257-b345-5621dd29d0c6"
REPLY_HANDLE = "@phagey"
RIVER_EMAIL = "river@arcade.dev"
# riv-relay skips any Linear post containing "Δ Delta", so every post is signed.
SIGNATURE = "~ Δ Delta, downstream of River"

FILED_KINDS = {"ask", "fyi", "optional"}
TITLE_PREFIX = {"ask": "", "fyi": "FYI: ", "optional": "Optional: "}
REQUIRED_FIELDS = {
    "ask": ("source", "title", "why", "ask", "default"),
    "fyi": ("source", "title", "why", "ask", "default"),
    "optional": ("source", "title", "why", "ask", "default"),
    "answer": ("source", "issue", "quote", "summary"),
}
PERMALINK = re.compile(
    r"^https://[\w-]+\.slack\.com/archives/(?P<conversation>[A-Z0-9]+)/p(?P<ts>\d{16})"
    r"(?:\?(?:.*&)?thread_ts=(?P<thread_ts>\d+\.\d+))?"
)
RIV_ID = re.compile(r"^RIV-\d+$")


class SlackTriageError(Exception):
    pass


def utc(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_utc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)


def now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


def is_dry_run() -> bool:
    return not DELIVER_FLAG.exists()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "window_start": FIRST_WINDOW_START,
        "consecutive_failures": 0,
        "messages": {},
        "threads": {},
    }


def save_state(state: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    partial = STATE_FILE.with_suffix(".tmp")
    partial.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    partial.replace(STATE_FILE)


def run_in_progress() -> bool:
    if not RUN_LEASE.exists():
        return False
    taken = parse_utc(json.loads(RUN_LEASE.read_text())["taken_at"])
    return now() - taken < RUN_LEASE_TTL


def release_run() -> None:
    RUN_LEASE.unlink(missing_ok=True)


def slack_keys(permalink: str) -> tuple[str, str]:
    """The message's key and its thread's key, both "<conversation>:<ts>"."""
    match = PERMALINK.match(permalink)
    if not match:
        raise SlackTriageError(f"not a Slack message permalink: {permalink}")
    conversation, digits = match["conversation"], match["ts"]
    message = f"{conversation}:{digits[:10]}.{digits[10:]}"
    thread_ts = match["thread_ts"]
    return message, f"{conversation}:{thread_ts}" if thread_ts else message


def validate(items: list) -> None:
    threads_seen = set()
    for number, item in enumerate(items, start=1):
        kind = item.get("kind") if isinstance(item, dict) else None
        if kind not in REQUIRED_FIELDS:
            raise SlackTriageError(
                f"item {number}: kind must be one of {sorted(REQUIRED_FIELDS)}, got {kind!r}"
            )
        missing = [f for f in REQUIRED_FIELDS[kind] if not str(item.get(f, "")).strip()]
        if missing:
            raise SlackTriageError(
                f"item {number} ({kind}): missing {', '.join(missing)}"
            )
        if kind == "answer" and not RIV_ID.match(item["issue"]):
            raise SlackTriageError(f"item {number}: issue must look like RIV-12")
        _, thread = slack_keys(item["source"])
        if kind in FILED_KINDS:
            if thread in threads_seen:
                raise SlackTriageError(
                    f"item {number}: two items for one Slack thread; combine them into one"
                )
            threads_seen.add(thread)


def refs_lines(item: dict) -> list[str]:
    return [f"- Slack: {item['source']}", *(f"- {ref}" for ref in item.get("refs", []))]


def suggested_reply_lines(item: dict) -> list[str]:
    reply = item.get("suggested_reply", "").strip()
    if not reply:
        return []
    return [
        "**Suggested reply:**",
        "",
        *(f"> {line}" for line in reply.splitlines()),
        "",
    ]


def reply_verbs() -> str:
    return (
        f"Reply here: `{REPLY_HANDLE} send` posts the suggested reply, "
        f"`{REPLY_HANDLE} send: <text>` posts your text, `{REPLY_HANDLE} done` or "
        f"`{REPLY_HANDLE} drop` closes this, or ask for anything else. Nothing goes "
        "to Slack without your approval of the exact text."
    )


def issue_description(item: dict) -> str:
    return "\n".join(
        [
            f"**Why:** {item['why']}",
            "",
            f"**Ask:** {item['ask']}",
            "",
            f"**Default:** {item['default']}",
            "",
            *suggested_reply_lines(item),
            "**Refs:**",
            *refs_lines(item),
            "",
            reply_verbs(),
            "",
            SIGNATURE,
        ]
    )


def thread_update(item: dict) -> str:
    return "\n".join(
        [
            f"New in the Slack thread: {item['source']}",
            "",
            f"**Why:** {item['why']}",
            "",
            f"**Ask:** {item['ask']}",
            "",
            *suggested_reply_lines(item),
            reply_verbs(),
            "",
            SIGNATURE,
        ]
    )


def relayed_answer(item: dict) -> str:
    quote = [f"> {line}" for line in item["quote"].splitlines()]
    return "\n".join(
        [
            f"Answer from Slack: {item['source']}",
            "",
            *quote,
            "",
            f"**Summary:** {item['summary']}",
            "",
            SIGNATURE,
        ]
    )


def title_for(item: dict) -> str:
    prefix = TITLE_PREFIX[item["kind"]]
    title = item["title"].strip()
    return title if not prefix or title.startswith(prefix) else prefix + title


def calls_for(item: dict, state: dict) -> list[dict]:
    """The Linear calls one item needs, or none if its message is already handled."""
    message, thread = slack_keys(item["source"])
    if message in state["messages"]:
        return []
    if item["kind"] == "answer":
        inputs = {"issue": item["issue"], "body": relayed_answer(item)}
        return [
            {
                "step": "comment",
                "tool_name": "Linear.AddComment",
                "inputs": inputs,
                "riv": item["issue"],
            }
        ]
    riv = state["threads"].get(thread)
    if riv:
        return [
            {
                "step": "comment",
                "tool_name": "Linear.AddComment",
                "inputs": {"issue": riv, "body": thread_update(item)},
                "riv": riv,
            },
            {
                "step": "update",
                "tool_name": "Linear.UpdateIssue",
                "inputs": {
                    "issue_id": riv,
                    "state": TODO_STATE,
                    "labels_to_add": [NEEDS_RIVER_LABEL_ID],
                },
                "riv": riv,
            },
        ]
    inputs = {
        "team": TEAM,
        "title": title_for(item),
        "description": issue_description(item),
        "state": TODO_STATE,
        "labels_to_add": [NEEDS_RIVER_LABEL_ID, AGENT_LABEL_ID, SLACK_LABEL_ID],
        "assignee": RIVER_EMAIL,
    }
    return [
        {
            "step": "create",
            "tool_name": "Linear.CreateIssue",
            "inputs": inputs,
            "riv": None,
        }
    ]


def log_dry_run(lines: list[str]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with DRY_RUN_LOG.open("a") as log:
        log.write("\n".join([f"=== {utc(now())} {lines[0]}", *lines[1:]]) + "\n\n")


def run(binary: str, args: list[str]) -> str:
    result = subprocess.run([binary, *args], capture_output=True, text=True)
    if result.returncode != 0:
        raise SlackTriageError(
            f"{Path(binary).name} {' '.join(args[:2])} exited {result.returncode}: "
            f"{result.stderr.strip()[:300]}"
        )
    return result.stdout


def escalate(reason: str) -> None:
    run(
        GT,
        [
            "escalate",
            f"slack-triage failed {ESCALATE_AFTER_FAILURES} runs in a row",
            "--severity",
            "medium",
            "--source",
            "plugin:slack-triage",
            "--fingerprint",
            "slack-triage",
            "--reason",
            reason,
        ],
    )


def advance_window(state: dict) -> None:
    state["window_start"] = state.pop("window_end")
    state["consecutive_failures"] = 0
    save_state(state)
    release_run()


def command_begin() -> str:
    if run_in_progress():
        return "BUSY"
    state = load_state()
    start = parse_utc(state["window_start"])
    end = min(now(), start + MAX_WINDOW)
    state["window_end"] = utc(end)
    save_state(state)
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    for leftover in PENDING_DIR.glob("*.json"):
        leftover.unlink()
    RUN_LEASE.write_text(json.dumps({"taken_at": utc(now())}) + "\n")
    return f"WINDOW {state['window_start']} {state['window_end']}"


def command_plan(raw: str) -> str:
    state = load_state()
    if "window_end" not in state or not RUN_LEASE.exists():
        raise SlackTriageError("plan ran without a window; run begin first")
    items = json.loads(raw or "[]")
    if not isinstance(items, list):
        raise SlackTriageError("plan expects a JSON array of items")
    validate(items)
    plan, call_lines, number = [], [], 0
    for item in items:
        calls = calls_for(item, state)
        for call in calls:
            number += 1
            call["id"] = f"c{number}"
            call_lines.append(
                f"CALL {call['id']} "
                + json.dumps(
                    {"tool_name": call["tool_name"], "inputs": call["inputs"]},
                    ensure_ascii=False,
                )
            )
        if calls:
            plan.append(
                {"source": item["source"], "kind": item["kind"], "calls": calls}
            )
    window = f"{state['window_start']}..{state['window_end']}"
    if not plan:
        advance_window(state)
        return f"DONE slack-triage: nothing new for River in {window}"
    if is_dry_run():
        for line in call_lines:
            _, call_id, payload = line.split(" ", 2)
            log_dry_run(
                [
                    f"WOULD CALL {call_id}",
                    json.dumps(json.loads(payload), indent=2, ensure_ascii=False),
                ]
            )
        advance_window(state)
        return f"DONE slack-triage (dry-run): {len(plan)} item(s) logged for {window}"
    PLAN_FILE.write_text(json.dumps(plan, indent=2, ensure_ascii=False) + "\n")
    return "\n".join([f"CALLS {len(call_lines)}", *call_lines])


def check_result(call: dict, result: dict) -> None:
    """Raise unless the saved result is the success shape of the call's tool."""
    issue = result.get("issue") or {}
    if call["step"] == "create":
        ok = result.get("created") is True and RIV_ID.match(issue.get("identifier", ""))
    elif call["step"] == "comment":
        ok = bool(result.get("id")) and result.get("issue_identifier") == call["riv"]
    else:
        ok = issue.get("identifier") == call["riv"]
    if not ok:
        raise SlackTriageError(
            f"{call['id']} ({call['tool_name']}) result is not a success: {json.dumps(result)[:300]}"
        )


def apply_item(state: dict, item: dict) -> str | None:
    """Record one item if all its calls succeeded. Returns why it stopped, or None."""
    message, thread = slack_keys(item["source"])
    riv = None
    for call in item["calls"]:
        saved = PENDING_DIR / f"{call['id']}.json"
        if not saved.exists():
            return f"{call['id']} ({call['tool_name']} for {item['source']}) has no saved result"
        try:
            result = json.loads(saved.read_text())
            check_result(call, result)
        except (ValueError, SlackTriageError) as error:
            return str(error)
        riv = result["issue"]["identifier"] if call["step"] == "create" else call["riv"]
    state["messages"][message] = riv
    if item["kind"] in FILED_KINDS:
        state["threads"].setdefault(thread, riv)
    save_state(state)
    return None


def command_apply(reason: str) -> str:
    if not PLAN_FILE.exists():
        raise SlackTriageError("apply ran without a plan; run begin and plan first")
    state = load_state()
    plan = json.loads(PLAN_FILE.read_text())
    problems = [p for p in (apply_item(state, item) for item in plan) if p]
    for leftover in PENDING_DIR.glob("*.json"):
        leftover.unlink()
    if problems:
        detail = "; ".join(filter(None, [reason, *problems]))
        raise SlackTriageError(
            f"{len(problems)} of {len(plan)} item(s) not written; the window is re-read next run: {detail}"
        )
    window = f"{state['window_start']}..{state['window_end']}"
    filed = sum(1 for item in plan if item["calls"][0]["step"] == "create")
    advance_window(state)
    return f"slack-triage: {filed} issue(s) filed, {len(plan) - filed} comment(s) for {window}"


def command_fail(reason: str) -> str:
    state = load_state()
    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
    save_state(state)
    release_run()
    failures = state["consecutive_failures"]
    if failures == ESCALATE_AFTER_FAILURES:
        escalate(reason)
        return f"slack-triage: failure {failures} in a row, escalated: {reason}"
    return f"slack-triage: failure {failures} in a row: {reason}"


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    reason = " ".join(argv[2:])
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if command == "begin":
                print(command_begin())
            elif command == "plan":
                print(command_plan(sys.stdin.read()))
            elif command == "apply":
                print(command_apply(reason))
            elif command == "fail":
                print(command_fail(reason or "unspecified"))
            else:
                print(__doc__, file=sys.stderr)
                return 2
        except Exception as error:
            if command == "fail":
                raise
            print(f"slack-triage {command} failed: {error}", file=sys.stderr)
            print(command_fail(f"{command}: {error}"), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
