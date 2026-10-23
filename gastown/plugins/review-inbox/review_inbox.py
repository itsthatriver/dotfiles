#!/usr/bin/env python3
"""Turn River's GitHub review requests into issues on Linear team RIV.

This script reads GitHub itself with gh and owns every decision: which PRs are
new, which tracked PRs moved, what to write to Linear, and when to mail or
escalate. Only an LLM session can call the Arcade gateway, so the review-inbox
dog makes the Linear calls this script prints and saves their results.

    review_inbox.py check           Reads GitHub and diffs it against state.
                                    Prints NOTHING_CHANGED, DONE <summary>, or
                                    CALLS <n> then one "CALL <id> <json>" line
                                    per Linear call for the dog to make.
    review_inbox.py apply [reason]  Reads pending/<id>.json for each call the
                                    dog made, records the results, and sends
                                    any mails. A reason says which call failed.
    review_inbox.py fail <reason>   Records a failed run; escalates on the 5th
                                    in a row.

Delivery is off until the file DELIVER exists in the runtime directory; until
then check appends every Linear call and mail it would make to dry-run.log,
makes none, and records the PR as if it had.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

RUNTIME_DIR = Path(
    os.environ.get("REVIEW_INBOX_HOME", Path.home() / "gt/.runtime/review-inbox")
)
STATE_FILE = RUNTIME_DIR / "state.json"
PENDING_DIR = RUNTIME_DIR / "pending"
PLAN_FILE = PENDING_DIR / "plan.json"
DRY_RUN_LOG = RUNTIME_DIR / "dry-run.log"
DELIVER_FLAG = RUNTIME_DIR / "DELIVER"
LOCK_FILE = RUNTIME_DIR / "review-inbox.lock"
GH = os.environ.get("REVIEW_INBOX_GH", "gh")
GT = os.environ.get("REVIEW_INBOX_GT", "gt")

SEARCH_QUERY = "user-review-requested:@me"
TEAM = "RIV"
TODO_STATE = "Todo"
DONE_STATE = "Done"
NEEDS_RIVER_LABEL_ID = "66b00900-266c-4e29-986a-8498b980185b"
RIVER_EMAIL = "river@arcade.dev"
# riv-relay skips any Linear post containing "Δ Delta", so every post is signed.
SIGNATURE = "~ Δ Delta, downstream of River"
REVIEW_DISPATCHER = "monorepo/crew/gigi"
LARGE_PR_LINES = 500
HIGH_RISK_LABEL = "risk:high"
RISK_LABEL = re.compile(r"^(risk:[\w-]+|review:human-only)$")
ESCALATE_AFTER_FAILURES = 5
DRY_RUN_ISSUE = "dry-run"

PR_QUERY = """
query($owner: String!, $name: String!, $number: Int!) {
  viewer { login }
  repository(owner: $owner, name: $name) {
    pullRequest(number: $number) {
      title url state body additions deletions changedFiles headRefOid
      author { login }
      labels(first: 50) { nodes { name } }
      reviewRequests(first: 50) {
        nodes { asCodeOwner requestedReviewer { ... on User { login } } }
      }
      reviews(last: 50) {
        nodes { id state submittedAt author { login } commit { oid } }
      }
    }
  }
}
"""

COMMENTS = {
    "reviewed": "River submitted a review ({review}) on {link}. Moving to Done.",
    "withdrawn": "The review request on {link} was withdrawn. Moving to Done.",
    "merged": "{link} was merged. Moving to Done.",
    "closed": "{link} was closed without merging. Moving to Done.",
    "new-commits": "New commits landed on {link} after River's review (head {head}). Flagging needs-river.",
    "rerequested": "River's review was requested again on {link}. Flagging needs-river.",
}
DONE_EVENTS = {"reviewed", "withdrawn", "merged", "closed"}
FLAG_EVENTS = {"new-commits", "rerequested"}
NEXT_PHASE = {
    "create": "requested",
    "resume": "requested",
    "rerequested": "requested",
    "reviewed": "reviewed",
    "new-commits": "changed",
    "withdrawn": "withdrawn",
    "merged": "closed",
    "closed": "closed",
}
# Headings, tables, images, and the issue-link lines PR templates start with.
SUMMARY_SKIP = re.compile(
    r"^(#|<!--|-->|---|\||!\[|(closes|fixes|part of|linear (issue|ticket):)(\s|$))",
    re.I,
)
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)


class ReviewInboxError(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def is_dry_run() -> bool:
    return not DELIVER_FLAG.exists()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"consecutive_failures": 0, "prs": {}}


def save_state(state: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    partial = STATE_FILE.with_suffix(".tmp")
    partial.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    partial.replace(STATE_FILE)


def run(binary: str, args: list[str], stdin: str | None = None) -> str:
    result = subprocess.run(
        [binary, *args], input=stdin, capture_output=True, text=True
    )
    if result.returncode != 0:
        name = Path(binary).name
        raise ReviewInboxError(
            f"{name} {' '.join(args[:2])} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def search_requests() -> dict[str, dict]:
    """Open PRs that request River's review directly, keyed "<owner/repo>#<number>"."""
    output = run(
        GH,
        ["search", "prs", "--state=open", SEARCH_QUERY]
        + ["--json", "repository,number,title,url", "--limit", "200"],
    )
    return {
        f"{pr['repository']['nameWithOwner']}#{pr['number']}": pr
        for pr in json.loads(output or "[]")
    }


def fetch_pr(key: str) -> dict:
    repo, number = key.split("#")
    owner, name = repo.split("/")
    response = json.loads(
        run(
            GH,
            ["api", "graphql", "-f", f"query={PR_QUERY}"]
            + ["-F", f"owner={owner}", "-F", f"name={name}", "-F", f"number={number}"],
        )
    )
    if response.get("errors"):
        raise ReviewInboxError(f"GitHub could not read {key}: {response['errors']}")
    return parse_pr(key, response["data"])


def parse_pr(key: str, data: dict) -> dict:
    login = data["viewer"]["login"]
    pr = data["repository"]["pullRequest"]
    request = next(
        (
            r
            for r in pr["reviewRequests"]["nodes"]
            if (r.get("requestedReviewer") or {}).get("login") == login
        ),
        None,
    )
    reviews = [
        r
        for r in pr["reviews"]["nodes"]
        if (r.get("author") or {}).get("login") == login
    ]
    latest = max(reviews, key=lambda r: r["submittedAt"] or "", default=None)
    return {
        "key": key,
        "title": pr["title"],
        "url": pr["url"],
        "state": pr["state"],
        "body": pr["body"] or "",
        "author": (pr.get("author") or {}).get("login", "ghost"),
        "additions": pr["additions"],
        "deletions": pr["deletions"],
        "changed_files": pr["changedFiles"],
        "head": pr["headRefOid"],
        "labels": [label["name"] for label in pr["labels"]["nodes"]],
        "requested": request is not None,
        "as_code_owner": request["asCodeOwner"] if request else None,
        "review": None
        if latest is None
        else {
            "id": latest["id"],
            "state": latest["state"],
            "commit": (latest.get("commit") or {}).get("oid"),
        },
    }


def is_created(record: dict | None) -> bool:
    if record is None or not record.get("riv"):
        return False
    # Issues recorded during a dry run were never created.
    return record["riv"] != DRY_RUN_ISSUE or is_dry_run()


def needs_detail(record: dict | None, in_search: bool) -> bool:
    if not is_created(record):
        return in_search
    phase = record["phase"]
    if in_search:
        return phase != "requested"
    return phase in ("requested", "reviewed", "changed")


def review_id(pr: dict) -> str | None:
    return pr["review"]["id"] if pr["review"] else None


def next_event(record: dict | None, in_search: bool, pr: dict | None) -> str | None:
    """The one transition a PR makes this run, or None. pr is read when needs_detail."""
    if not is_created(record):
        return "create" if in_search else None
    phase = record["phase"]
    if in_search:
        if phase == "requested":
            return None
        # New commits already flagged needs-river; a re-request adds nothing.
        return "resume" if phase == "changed" else "rerequested"
    if phase in ("withdrawn", "closed"):
        return None
    if pr["state"] != "OPEN":
        return "merged" if pr["state"] == "MERGED" else "closed"
    reviewed_since = review_id(pr) not in (None, record.get("review_id"))
    if phase == "requested":
        if pr["requested"]:
            # GitHub's search index lags the PR itself.
            return None
        return "reviewed" if reviewed_since else "withdrawn"
    if phase == "reviewed":
        return "new-commits" if pr["head"] != record.get("review_commit") else None
    return "reviewed" if reviewed_since else None


def is_heavy(pr: dict) -> bool:
    return (
        pr["additions"] + pr["deletions"] > LARGE_PR_LINES
        or HIGH_RISK_LABEL in pr["labels"]
    )


def why_tagged(pr: dict) -> str:
    if pr["as_code_owner"] is True:
        return "direct request, as a CODEOWNER"
    if pr["as_code_owner"] is False:
        return "direct request, added manually"
    return "direct request"


def summary_lines(body: str, count: int = 2, limit: int = 200) -> list[str]:
    lines = []
    for raw in HTML_COMMENT.sub("", body).splitlines():
        line = raw.strip().lstrip("-*> ").strip()
        if not line or SUMMARY_SKIP.match(line):
            continue
        lines.append(line if len(line) <= limit else line[: limit - 1] + "…")
        if len(lines) == count:
            break
    return lines or ["(The PR has no description.)"]


def link(key: str, url: str) -> str:
    return f"[{key}]({url})"


def issue_description(pr: dict) -> str:
    risk = [label for label in pr["labels"] if RISK_LABEL.match(label)]
    return "\n".join(
        [
            f"River was asked to review {link(pr['key'], pr['url'])}.",
            "",
            f"- **Author:** @{pr['author']}",
            f"- **Size:** +{pr['additions']} / -{pr['deletions']} across {pr['changed_files']} file(s)",
            f"- **Risk:** {', '.join(risk) if risk else 'no risk label'}",
            f"- **Why River:** {why_tagged(pr)}",
            "",
            *(f"> {line}" for line in summary_lines(pr["body"])),
            "",
            f"PR: {pr['key']}",
            "",
            SIGNATURE,
        ]
    )


def calls_for(event: str, record: dict | None, pr: dict | None) -> list[dict]:
    if event == "create":
        inputs = {
            "team": TEAM,
            "title": f"Review: #{pr['key'].split('#')[1]} {pr['title']}",
            "description": issue_description(pr),
            "state": TODO_STATE,
            "labels_to_add": [NEEDS_RIVER_LABEL_ID],
            "assignee": RIVER_EMAIL,
        }
        return [{"step": "create", "tool_name": "Linear.CreateIssue", "inputs": inputs}]
    if event == "resume":
        return []
    riv = record["riv"]
    text = COMMENTS[event].format(
        link=link(record["key"], record["url"]),
        review=(
            pr["review"]["state"].lower().replace("_", " ") if pr["review"] else ""
        ),
        head=pr["head"][:7] if pr else "",
    )
    update = (
        {"issue_id": riv, "state": DONE_STATE}
        if event in DONE_EVENTS
        else {"issue_id": riv, "labels_to_add": [NEEDS_RIVER_LABEL_ID]}
    )
    return [
        {
            "step": "comment",
            "tool_name": "Linear.AddComment",
            "inputs": {"issue": riv, "body": f"{text}\n\n{SIGNATURE}"},
        },
        {"step": "update", "tool_name": "Linear.UpdateIssue", "inputs": update},
    ]


def settled_record(record: dict | None, event: str, key: str, pr: dict | None) -> dict:
    """The record to store once every call for the event has succeeded."""
    settled = dict(record or {"key": key})
    settled["phase"] = NEXT_PHASE[event]
    settled.pop("partial", None)
    if pr:
        settled.update(key=key, title=pr["title"], url=pr["url"])
    if event in ("create", "resume", "rerequested"):
        settled["review_id"] = review_id(pr)
    if event == "create":
        settled["mail"] = "pending" if is_heavy(pr) else None
        settled["heavy_reason"] = heavy_reason(pr)
    if event == "reviewed":
        settled["review_id"] = review_id(pr)
        settled["review_commit"] = pr["review"]["commit"]
    return settled


def heavy_reason(pr: dict) -> str:
    reasons = []
    lines = pr["additions"] + pr["deletions"]
    if lines > LARGE_PR_LINES:
        reasons.append(f"{lines} changed lines (over {LARGE_PR_LINES})")
    if HIGH_RISK_LABEL in pr["labels"]:
        reasons.append(f"the {HIGH_RISK_LABEL} label")
    return " and ".join(reasons)


def review_mail(record: dict) -> dict:
    body = "\n".join(
        [
            f"River was asked to review {record['key']}: {record['title']}",
            record["url"],
            f"RIV: {record['riv']} {record.get('riv_url') or ''}".rstrip(),
            "",
            f"It has {record['heavy_reason']}. Please sling a read-only preliminary",
            f"review, like RIV-8: read the PR and post findings on {record['riv']}.",
            "No GitHub writes.",
            "",
            "Sent by the review-inbox plugin, which never slings and never writes to GitHub.",
        ]
    )
    subject = f"review-inbox: preliminary review for {record['key']}? ({record['riv']})"
    return {"to": REVIEW_DISPATCHER, "subject": subject, "body": body}


def log_dry_run(lines: list[str]) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with DRY_RUN_LOG.open("a") as log:
        log.write("\n".join([f"=== {now()} {lines[0]}", *lines[1:]]) + "\n\n")


def send_mail(mail: dict) -> None:
    if is_dry_run():
        log_dry_run(
            [f"WOULD SEND to {mail['to']}", f"Subject: {mail['subject']}", mail["body"]]
        )
        return
    run(
        GT, ["mail", "send", mail["to"], "-s", mail["subject"], "--stdin"], mail["body"]
    )


def send_pending_mails(state: dict) -> int:
    """Send review mails owed for created issues. A failed send is retried next run."""
    sent = 0
    for record in state["prs"].values():
        if record.get("mail") == "pending" and is_created(record):
            send_mail(review_mail(record))
            record["mail"] = "sent"
            save_state(state)
            sent += 1
    return sent


def escalate(reason: str) -> None:
    run(
        GT,
        [
            "escalate",
            f"review-inbox failed {ESCALATE_AFTER_FAILURES} runs in a row",
            "--severity",
            "medium",
            "--source",
            "plugin:review-inbox",
            "--fingerprint",
            "review-inbox",
            "--reason",
            reason,
        ],
    )


def planned_events(state: dict) -> list[dict]:
    requests = search_requests()
    keys = list(requests) + [k for k in state["prs"] if k not in requests]
    events = []
    for key in keys:
        record = state["prs"].get(key)
        in_search = key in requests
        pr = fetch_pr(key) if needs_detail(record, in_search) else None
        event = next_event(record, in_search, pr)
        if event is None:
            continue
        partial = (record or {}).get("partial") or {}
        done = partial.get("done", []) if partial.get("event") == event else []
        calls = [c for c in calls_for(event, record, pr) if c["step"] not in done]
        events.append(
            {
                "key": key,
                "event": event,
                "calls": calls,
                "settled": settled_record(record, event, key, pr),
            }
        )
    return events


def command_check() -> str:
    state = load_state()
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    # Results left by a failed run must never stand in for this run's calls.
    for leftover in PENDING_DIR.glob("*.json"):
        leftover.unlink()
    mails = 0 if is_dry_run() else send_pending_mails(state)
    events = planned_events(state)

    if is_dry_run():
        writes = 0
        for item in events:
            for call in item["calls"]:
                log_dry_run(
                    [
                        f"WOULD CALL {call['tool_name']} for {item['key']} ({item['event']})",
                        json.dumps(call["inputs"], indent=2, ensure_ascii=False),
                    ]
                )
                writes += 1
            record = item["settled"]
            if item["event"] == "create":
                record["riv"] = DRY_RUN_ISSUE
            state["prs"][item["key"]] = record
            save_state(state)
        mails = send_pending_mails(state)
        return finish(
            state,
            f"DONE review-inbox: {writes} Linear write(s) and {mails} mail(s) logged to dry-run.log for {len(events)} PR(s)",
            quiet=not events,
        )

    silent = [item for item in events if not item["calls"]]
    for item in silent:
        state["prs"][item["key"]] = item["settled"]
    save_state(state)
    calling = [item for item in events if item["calls"]]
    if not calling:
        return finish(
            state,
            f"DONE review-inbox: no Linear writes; {mails} mail(s) sent, {len(silent)} PR(s) updated",
            quiet=not (mails or silent),
        )

    lines, counter = [], 0
    for item in calling:
        for call in item["calls"]:
            counter += 1
            call["id"] = f"c{counter}"
            payload = {"tool_name": call["tool_name"], "inputs": call["inputs"]}
            lines.append(f"CALL {call['id']} {json.dumps(payload, ensure_ascii=False)}")
    PLAN_FILE.write_text(json.dumps(calling, indent=2, ensure_ascii=False) + "\n")
    return "\n".join([f"CALLS {counter}", *lines])


def finish(state: dict, summary: str, quiet: bool) -> str:
    state["consecutive_failures"] = 0
    save_state(state)
    return "NOTHING_CHANGED" if quiet else summary


def check_result(call: dict, result: dict, riv: str | None) -> None:
    """Raise unless the saved result is the success shape of the call's tool."""
    issue = result.get("issue") or {}
    if call["step"] == "create":
        ok = result.get("created") is True and re.match(
            r"^RIV-\d+$", issue.get("identifier", "")
        )
    elif call["step"] == "comment":
        ok = bool(result.get("id")) and result.get("issue_identifier") == riv
    else:
        ok = issue.get("identifier") == riv
    if not ok:
        raise ReviewInboxError(
            f"{call['id']} ({call['tool_name']}) result is not a success: {json.dumps(result)[:300]}"
        )


def apply_event(state: dict, item: dict) -> str | None:
    """Record each successful call of one event. Returns why it stopped, or None."""
    key = item["key"]
    record = dict(state["prs"].get(key) or {"key": key})
    partial = record.get("partial") or {}
    if partial.get("event") != item["event"]:
        partial = {"event": item["event"], "done": []}
    for call in item["calls"]:
        saved = PENDING_DIR / f"{call['id']}.json"
        if not saved.exists():
            return f"{call['id']} ({call['tool_name']} for {key}) has no saved result"
        try:
            result = json.loads(saved.read_text())
            check_result(call, result, record.get("riv"))
        except (ValueError, ReviewInboxError) as error:
            return str(error)
        if call["step"] == "create":
            record.update(
                riv=result["issue"]["identifier"], riv_url=result["issue"].get("url")
            )
        partial["done"] = [*partial["done"], call["step"]]
        record["partial"] = partial
        state["prs"][key] = record
        save_state(state)
    settled = dict(item["settled"])
    for field in ("riv", "riv_url"):
        if field in record:
            settled[field] = record[field]
    state["prs"][key] = settled
    save_state(state)
    return None


def command_apply(reason: str) -> str:
    if not PLAN_FILE.exists():
        raise ReviewInboxError("apply ran without a plan; run check first")
    state = load_state()
    plan = json.loads(PLAN_FILE.read_text())
    problems = [p for p in (apply_event(state, item) for item in plan) if p]
    mails = send_pending_mails(state)
    for leftover in PENDING_DIR.glob("*.json"):
        leftover.unlink()
    done = len(plan) - len(problems)
    if problems:
        detail = "; ".join(filter(None, [reason, *problems]))
        raise ReviewInboxError(
            f"{len(problems)} of {len(plan)} PR(s) not written, retrying next run: {detail}"
        )
    state["consecutive_failures"] = 0
    save_state(state)
    return f"review-inbox: {done} PR(s) written to RIV, {mails} mail(s) sent"


def command_fail(reason: str) -> str:
    state = load_state()
    state["consecutive_failures"] = state.get("consecutive_failures", 0) + 1
    save_state(state)
    failures = state["consecutive_failures"]
    if failures == ESCALATE_AFTER_FAILURES:
        escalate(reason)
        return f"review-inbox: failure {failures} in a row, escalated: {reason}"
    return f"review-inbox: failure {failures} in a row: {reason}"


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    reason = " ".join(argv[2:])
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        try:
            if command == "check":
                print(command_check())
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
            print(f"review-inbox {command} failed: {error}", file=sys.stderr)
            print(command_fail(f"{command}: {error}"), file=sys.stderr)
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
