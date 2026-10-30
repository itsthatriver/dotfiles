#!/usr/bin/env python3
"""Relay River's activity on Linear team RIV to Gas Town agents via gt mail.

The riv-relay dog reads Linear through the Arcade gateway (only an LLM session
can call it) and hands what it read to this script, which owns every decision:
what changed, what to relay, who receives it, and what state to keep.

    relay.py check           stdin: one "<identifier> <updated_at>" line per
                             RIV issue. Prints NOTHING_CHANGED, or
                             FETCH <identifier>... for issues to read in full.
    relay.py relay           Reads pending/<identifier>.json for each fetched
                             issue, then logs (dry run) or sends the mails.
    relay.py fail <reason>   Records a failed run; escalates on the 5th in a row.

Delivery is off until the file DELIVER exists in the runtime directory; until
then every mail is appended to dry-run.log instead of being sent.
"""

from __future__ import annotations

import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RUNTIME_DIR = Path(
    os.environ.get("RIV_RELAY_HOME", Path.home() / "gt/.runtime/riv-relay")
)
STATE_FILE = RUNTIME_DIR / "state.json"
PENDING_DIR = RUNTIME_DIR / "pending"
LISTING_FILE = PENDING_DIR / "listing.txt"
# The issues this run was asked to fetch. Anything else that changed waits.
BATCH_FILE = PENDING_DIR / "batch.txt"
# A dog copies each fetched issue into a snapshot by hand, so one run can
# only take a few. A backlog drains over several runs.
DEFAULT_MAX_FETCH = 6
DRY_RUN_LOG = RUNTIME_DIR / "dry-run.log"
DELIVER_FLAG = RUNTIME_DIR / "DELIVER"
LOCK_FILE = RUNTIME_DIR / "relay.lock"
# A run spans check → the dog's fetches → relay, so it holds a lease across all
# three. Without it, a second dog's check wipes the first dog's snapshots.
RUN_LEASE = RUNTIME_DIR / "run.lease"
GT = os.environ.get("RIV_RELAY_GT", "gt")

# Agents post to Linear as River's user, so authorship can't separate them from
# River. Every agent post is signed; Linear stores the leading "~" escaped.
AGENT_SIGNATURE = "Δ Delta"
NEEDS_RIVER = "needs-river"
TERMINAL_STATE_TYPES = {"completed", "canceled"}
KNOWN_CREW = ("phagey", "gigi")
DEFAULT_RECIPIENT = "monorepo/crew/gigi"
CURSOR_OVERLAP = timedelta(minutes=5)
# Two runs of the 5-minute gate: an agent's signed comment this close before a
# move to Done or Canceled marks the move as the agent's.
AGENT_CLOSE_WINDOW = timedelta(minutes=10)
ESCALATE_AFTER_FAILURES = 5
# Longer than any run takes; a lease this old belongs to a run that died.
RUN_LEASE_TTL = timedelta(minutes=20)
EPOCH = "1970-01-01T00:00:00.000Z"

MENTION = re.compile(r"(?<![\w@])@(" + "|".join(KNOWN_CREW) + r")\b", re.IGNORECASE)
AGENT_LABEL = re.compile(r"^agent:([\w-]+)$")
AGENT_FOOTER = re.compile(r"^\s*Agent:\s*`?(monorepo/crew/[\w-]+)`?\s*$", re.MULTILINE)
BEAD_FOOTER = re.compile(r"^\s*Bead:\s*`?(mo-[\w.-]+)`?", re.MULTILINE)
CHECKBOX = re.compile(r"^\s*[-*]\s+\[([ xX])\]\s+(.*?)\s*$")


class RelayError(Exception):
    pass


def parse_time(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def format_time(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def is_dry_run() -> bool:
    return not DELIVER_FLAG.exists()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    # A fresh dry run replays all history so it can be checked against what
    # actually happened; fresh delivery starts from now so nothing old is sent.
    start = EPOCH if is_dry_run() else format_time(datetime.now(timezone.utc))
    return {"cursor": start, "consecutive_failures": 0, "issues": {}}


def save_state(state: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    partial = STATE_FILE.with_suffix(".tmp")
    partial.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    partial.replace(STATE_FILE)


def is_agent_post(body: str) -> bool:
    return AGENT_SIGNATURE in body


def closed_by_agent(issue: dict) -> bool:
    """True when the issue's latest comment is an agent's, posted just before the move.

    Linear's completed_at dates a move to Done; nothing dates a move to
    Canceled, so updated_at stands in for it.
    """
    comments = issue.get("comments") or []
    if not comments:
        return False
    latest = max(comments, key=lambda c: c["created_at"])
    moved_at = parse_time(issue.get("completed_at") or issue["updated_at"])
    posted_at = parse_time(latest["created_at"])
    return (
        is_agent_post(latest["body"])
        and moved_at - AGENT_CLOSE_WINDOW <= posted_at <= moved_at
    )


def comment_key(comment: dict) -> str:
    return (
        comment.get("edited_at")
        or comment.get("editedAt")
        or digest(comment.get("body", ""))
    )


def label_names(issue: dict) -> list[str]:
    return [
        label["name"] if isinstance(label, dict) else label
        for label in issue.get("labels") or []
    ]


def checkboxes(description: str) -> dict[str, bool]:
    boxes = {}
    for line in description.splitlines():
        match = CHECKBOX.match(line)
        if match:
            boxes[match.group(2)] = match.group(1) != " "
    return boxes


def flipped_checkboxes(before: str, after: str) -> list[str]:
    old, new = checkboxes(before), checkboxes(after)
    return [
        f"[{'x' if checked else ' '}] {text}"
        for text, checked in new.items()
        if text in old and old[text] != checked
    ]


def route(issue: dict, comment_body: str | None) -> tuple[str, str]:
    """Pick the recipient, first match wins. Returns (address, reason)."""
    if comment_body:
        mention = MENTION.search(comment_body)
        if mention:
            name = mention.group(1).lower()
            return f"monorepo/crew/{name}", f"@{name} in the comment"
    for label in label_names(issue):
        match = AGENT_LABEL.match(label)
        if match:
            return f"monorepo/crew/{match.group(1)}", f"label {label}"
    footer = AGENT_FOOTER.search(issue.get("description") or "")
    if footer:
        return footer.group(1), "Agent: footer in the description"
    return DEFAULT_RECIPIENT, "default recipient"


def one_line(text: str, limit: int = 60) -> str:
    return " ".join(text.split())[:limit]


def comment_url(issue: dict, comment_id: str) -> str:
    return f"{issue['url']}#comment-{comment_id[:8]}"


def build_mail(issue: dict, event: dict) -> dict:
    ident = issue["identifier"]
    comment = event.get("comment")
    address, reason = route(issue, comment["body"] if comment else None)
    bead = BEAD_FOOTER.search(issue.get("description") or "")
    kind = event["kind"]

    if kind in ("comment", "edit"):
        verb = "commented" if kind == "comment" else "edited a comment"
        subject = f"[{ident}] River {verb}: {one_line(comment['body'])}"
        lead = [
            f"River {verb} on {ident}: {issue['title']}",
            comment_url(issue, comment["id"]),
            "",
            comment["body"],
        ]
    elif kind == "checkboxes":
        subject = f"[{ident}] River ticked boxes: {len(event['flips'])} changed"
        lead = [
            f"River changed checkboxes in the {ident} description: {issue['title']}",
            "",
            *event["flips"],
        ]
    elif kind == "needs-river-cleared":
        subject = f"[{ident}] River cleared {NEEDS_RIVER}"
        lead = [
            f"River removed {NEEDS_RIVER} from {ident} without commenting: {issue['title']}"
        ]
    else:
        subject = f"[{ident}] River closed it: {issue['state']['name']}"
        lead = [f"River moved {ident} to {issue['state']['name']}: {issue['title']}"]

    footer = [
        "",
        "---",
        f"Issue: {ident} ({issue['state']['name']}) {issue['url']}",
        f"Comment ID: {comment['id'] if comment else 'none'}",
        f"Parent comment ID: {(comment or {}).get('parent_id') or 'none'}",
        f"Bead: {bead.group(1) if bead else 'none'}",
        f"Routed to {address} by {reason}.",
        "Relayed by the riv-relay plugin. Answer River on Linear, not by replying to this mail.",
    ]
    return {"to": address, "subject": subject, "body": "\n".join(lead + footer)}


def diff_issue(
    issue: dict, previous: dict | None, cursor: str
) -> tuple[list[dict], dict]:
    """Compare a fetched issue with its stored record.

    Returns the events to relay, in order, and the record to store once every
    event has been relayed. Each event carries the fields it settles, so state
    can be committed one successful send at a time.
    """
    first_sight = previous is None
    record = dict(
        previous
        or {"comments": {}, "river_spoke_since_flag": False, "thread_root": None}
    )
    record["comments"] = dict(record["comments"])
    events = []

    needs_river = NEEDS_RIVER in label_names(issue)
    if not first_sight and needs_river and not previous["needs_river"]:
        record["river_spoke_since_flag"] = False

    for comment in sorted(issue.get("comments") or [], key=lambda c: c["created_at"]):
        key = comment_key(comment)
        known = record["comments"].get(comment["id"])
        if known == key:
            continue
        silent = is_agent_post(comment["body"]) or (
            known is None and first_sight and comment["created_at"] <= cursor
        )
        if silent:
            record["comments"][comment["id"]] = key
            continue
        kind = "comment" if known is None else "edit"
        events.append(
            {
                "kind": kind,
                "comment": comment,
                "settles": {"comment": (comment["id"], key)},
            }
        )

    if not first_sight and previous["needs_river"] and not needs_river:
        spoke = record["river_spoke_since_flag"] or any(
            e["kind"] in ("comment", "edit") for e in events
        )
        if not spoke:
            events.append({"kind": "needs-river-cleared", "settles": {}})

    description = issue.get("description") or ""
    if (
        first_sight
        or digest(description) == digest(record["description_relayed"])
        or not needs_river
    ):
        record["description_relayed"] = description
        record["description_pending"] = None
    elif record.get("description_pending") != digest(description):
        record["description_pending"] = digest(description)
    else:
        flips = flipped_checkboxes(record["description_relayed"], description)
        if flips:
            events.append(
                {
                    "kind": "checkboxes",
                    "flips": flips,
                    "settles": {"description": description},
                }
            )
        else:
            record["description_relayed"] = description
            record["description_pending"] = None

    state_type = issue["state"]["type"]
    if (
        not first_sight
        and state_type in TERMINAL_STATE_TYPES
        and previous["state_type"] not in TERMINAL_STATE_TYPES
        and not closed_by_agent(issue)
    ):
        events.append({"kind": "closed", "settles": {}})

    record.update(
        needs_river=needs_river, state_type=state_type, updated_at=issue["updated_at"]
    )
    return events, record


def settle(record: dict, event: dict) -> None:
    settles = event["settles"]
    if "comment" in settles:
        comment_id, key = settles["comment"]
        record["comments"][comment_id] = key
        record["river_spoke_since_flag"] = True
    if "description" in settles:
        record["description_relayed"] = settles["description"]
        record["description_pending"] = None


def run_gt(args: list[str], stdin: str | None = None) -> str:
    result = subprocess.run([GT, *args], input=stdin, capture_output=True, text=True)
    if result.returncode != 0:
        raise RelayError(
            f"gt {' '.join(args[:2])} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def find_sent_message_id(mail: dict) -> str | None:
    inbox = json.loads(run_gt(["mail", "inbox", mail["to"], "--json"]) or "[]")
    matches = [m for m in inbox if m.get("subject") == mail["subject"]]
    return (
        max(matches, key=lambda m: m.get("timestamp") or "")["id"] if matches else None
    )


def deliver(mail: dict, thread_root: str | None) -> str:
    """Log or send one mail. Returns the thread root to keep for the issue."""
    if is_dry_run():
        with DRY_RUN_LOG.open("a") as log:
            stamp = format_time(datetime.now(timezone.utc))
            log.write(
                f"=== {stamp} WOULD SEND to {mail['to']}\nSubject: {mail['subject']}\n{mail['body']}\n\n"
            )
        return thread_root or "dry-run"
    args = ["mail", "send", mail["to"], "-s", mail["subject"], "--stdin"]
    # Roots recorded during a dry run are placeholders, not message IDs.
    real_root = thread_root if thread_root and thread_root != "dry-run" else None
    if real_root:
        args += ["--reply-to", real_root]
    run_gt(args, stdin=mail["body"])
    return real_root or find_sent_message_id(mail)


def escalate(reason: str) -> None:
    title = f"riv-relay failed {ESCALATE_AFTER_FAILURES} runs in a row"
    run_gt(
        [
            "escalate",
            title,
            "--severity",
            "medium",
            "--source",
            "plugin:riv-relay",
            "--fingerprint",
            "riv-relay",
            "--reason",
            reason,
        ]
    )


def max_fetch() -> int:
    return max(1, int(os.environ.get("RIV_RELAY_MAX_FETCH", DEFAULT_MAX_FETCH)))


def needs_fetch(issues: dict, ident: str, updated_at: str) -> bool:
    # A pending description change is confirmed by reading the issue once more.
    known = issues.get(ident)
    return (
        known is None
        or known["updated_at"] != updated_at
        or bool(known.get("description_pending"))
    )


def in_progress(record: dict, previous: dict | None) -> dict:
    """The record to store while an issue's events are still being relayed.

    It keeps the previous updated_at, label and state, so a failed send leaves
    the issue looking unread and the unsent events are found again next run.
    """
    progress = dict(record, comments=dict(record["comments"]))
    if previous is None:
        progress["updated_at"] = None
    else:
        for field in ("updated_at", "needs_river", "state_type"):
            progress[field] = previous[field]
    return progress


def run_in_progress() -> bool:
    if not RUN_LEASE.exists():
        return False
    age = datetime.now(timezone.utc).timestamp() - RUN_LEASE.stat().st_mtime
    return age < RUN_LEASE_TTL.total_seconds()


def release_run() -> None:
    RUN_LEASE.unlink(missing_ok=True)


def command_check(lines: list[str]) -> str:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if run_in_progress():
            return "BUSY"
        RUN_LEASE.write_text(format_time(datetime.now(timezone.utc)))
    try:
        answer = check_listing(lines)
    except Exception:
        release_run()
        raise
    if answer == "NOTHING_CHANGED":
        release_run()
    return answer


def check_listing(lines: list[str]) -> str:
    state = load_state()
    listing = {}
    for line in lines:
        fields = line.split()
        if len(fields) < 2:
            continue
        parse_time(fields[1])
        listing[fields[0]] = fields[1]
    if not listing:
        raise RelayError(
            "check got no '<identifier> <updated_at>' lines; the Linear read returned nothing usable"
        )

    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    # A snapshot left by a failed run must never stand in for this run's read.
    for leftover in PENDING_DIR.glob("*.json"):
        leftover.unlink()
    LISTING_FILE.write_text(
        "".join(f"{ident} {stamp}\n" for ident, stamp in listing.items())
    )
    changed = sorted(
        (
            (parse_time(stamp), ident)
            for ident, stamp in listing.items()
            if needs_fetch(state["issues"], ident, stamp)
        ),
    )
    batch = [ident for _, ident in changed[: max_fetch()]]
    if batch:
        BATCH_FILE.write_text(" ".join(batch))
        return "FETCH " + " ".join(batch)
    LISTING_FILE.unlink()
    state["consecutive_failures"] = 0
    save_state(state)
    return "NOTHING_CHANGED"


def read_snapshot(ident: str) -> dict:
    snapshot = PENDING_DIR / f"{ident}.json"
    if not snapshot.exists():
        raise RelayError(f"check asked for {ident} but {snapshot} was not written")
    issue = json.loads(snapshot.read_text())
    return issue.get("issue", issue)


def command_relay() -> str:
    if not LISTING_FILE.exists():
        raise RelayError("relay ran without a listing; run check first")
    with LOCK_FILE.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state()
        listing = dict(
            line.split()
            for line in LISTING_FILE.read_text().splitlines()
            if line.strip()
        )
        issues = state["issues"]
        # Every issue in a run is judged against the cursor the run started with.
        cursor = state["cursor"]
        batch = set(BATCH_FILE.read_text().split()) if BATCH_FILE.exists() else None
        deferred = False
        sent = 0
        for ident, updated_at in listing.items():
            if not needs_fetch(issues, ident, updated_at):
                continue
            if batch is not None and ident not in batch:
                deferred = True
                continue
            issue = read_snapshot(ident)
            previous = issues.get(ident)
            events, record = diff_issue(issue, previous, cursor)
            progress = in_progress(record, previous)
            for event in events:
                progress["thread_root"] = deliver(
                    build_mail(issue, event), progress.get("thread_root")
                )
                settle(progress, event)
                settle(record, event)
                issues[ident] = progress
                save_state(state)
                sent += 1
            record["thread_root"] = progress.get("thread_root")
            issues[ident] = record
            save_state(state)
            (PENDING_DIR / f"{ident}.json").unlink()
        # A deferred issue is read in a later run against this same cursor, so a
        # new issue's recent comments aren't mistaken for history.
        if not deferred:
            newest = max(parse_time(stamp) for stamp in listing.values())
            state["cursor"] = max(cursor, format_time(newest - CURSOR_OVERLAP))
        LISTING_FILE.unlink()
        BATCH_FILE.unlink(missing_ok=True)
        state["consecutive_failures"] = 0
        save_state(state)
        release_run()
    mode = "logged to dry-run.log" if is_dry_run() else "sent"
    return f"riv-relay: {sent} mail(s) {mode} from {len(listing)} RIV issue(s)"


def command_fail(reason: str) -> str:
    release_run()
    state = load_state()
    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
    save_state(state)
    failures = state["consecutive_failures"]
    if failures == ESCALATE_AFTER_FAILURES:
        escalate(reason)
        return f"riv-relay: failure {failures} in a row, escalated: {reason}"
    return f"riv-relay: failure {failures} in a row: {reason}"


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    try:
        if command == "check":
            print(command_check(sys.stdin.read().splitlines()))
        elif command == "relay":
            print(command_relay())
        elif command == "fail":
            print(command_fail(" ".join(argv[2:]) or "unspecified"))
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except Exception as error:
        if command == "fail":
            raise
        print(f"riv-relay {command} failed: {error}", file=sys.stderr)
        print(command_fail(f"{command}: {error}"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
