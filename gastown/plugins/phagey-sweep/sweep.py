#!/usr/bin/env python3
"""Check for anything that needs phagey's judgement, and wake phagey once if so.

The phagey-sweep dog reads Linear through the Arcade gateway (only an LLM
session can call it) and hands the raw JSON to this script, which owns every
decision: which comments count, what GitHub and the machine say, what has
already been reported, and who gets mailed.

    sweep.py begin             Takes the run lease. Prints BUSY, or
                               CURSOR <iso> to use as created_after.
    sweep.py ingest <feed>     stdin: one raw Linear.ListRecentComments result.
                               feed is "plt" or "handle". Once per page.
    sweep.py run               Filters, checks GitHub and health, then mails
                               phagey one digest (or logs it in a dry run).
    sweep.py fail <reason>     Records a failed run; mails phagey on the 3rd in a row.

Delivery is off until the file DELIVER exists in the runtime directory; until
then every mail is appended to dry-run.log instead of being sent.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

RUNTIME_DIR = Path(
    os.environ.get("PHAGEY_SWEEP_HOME", Path.home() / "gt/.runtime/phagey-sweep")
)
STATE_FILE = RUNTIME_DIR / "state.json"
PENDING_DIR = RUNTIME_DIR / "pending"
DRY_RUN_LOG = RUNTIME_DIR / "dry-run.log"
DELIVER_FLAG = RUNTIME_DIR / "DELIVER"
LOCK_FILE = RUNTIME_DIR / "sweep.lock"
# A run spans begin, the dog's reads and run, so it holds a lease across all of
# them. Without it a second dog's begin would wipe the first dog's pages.
RUN_LEASE = RUNTIME_DIR / "run.lease"
RUN_LEASE_TTL = timedelta(minutes=20)

TOWN = Path(os.environ.get("PHAGEY_SWEEP_TOWN", Path.home() / "gt"))
GT = os.environ.get("PHAGEY_SWEEP_GT", "gt")
TOOLS = Path.home() / ".local/share/phagey-tools"
GH_SCRIPT = os.environ.get("PHAGEY_SWEEP_GH_SCRIPT", TOOLS / "gh-phagey-mentions.sh")
DELEGATES_SCRIPT = os.environ.get(
    "PHAGEY_SWEEP_DELEGATES_SCRIPT", TOOLS / "check-delegates.sh"
)
GH_TIMEOUT_SECONDS = 90
DELEGATES_TIMEOUT_SECONDS = 150
DISK_PATH = os.environ.get("PHAGEY_SWEEP_DISK_PATH", "/System/Volumes/Data")

PHAGEY = "monorepo/crew/phagey"
FEEDS = ("plt", "handle")
# Handle used in River's requests to phagey; the gh script and the dog's
# body_contains filter match it the same way.
HANDLE = "phagey:"
# Agents post under River's account, so authorship can't separate them from
# River. Every agent post is signed; Linear stores the leading "~" escaped
# ("\~ Δ Delta"), which this substring covers too.
AGENT_SIGNATURE = "Δ Delta"
# riv-relay already relays River's comments on these teams.
RELAYED_TEAMS = ("RIV",)

# A fresh state looks back a day, so the first dry run has something to show.
INITIAL_LOOKBACK = timedelta(days=1)
# Re-read a little before the last run so a comment Linear was slow to surface
# is still found; the seen set stops it being reported twice.
CURSOR_OVERLAP = timedelta(minutes=5)
SEEN_RETENTION = timedelta(days=7)
# A health problem is mailed when it appears, and again if it outlasts this.
HEALTH_REMIND_AFTER = timedelta(hours=6)
FAIL_MAIL_AT = 3
EXCERPT_CHARS = 300
DEFAULT_MIN_DISK_GIB = 60


class SweepError(Exception):
    pass


def now() -> datetime:
    return datetime.now(timezone.utc)


def parse_time(stamp: str) -> datetime:
    return datetime.fromisoformat(stamp.replace("Z", "+00:00"))


def format_time(moment: datetime) -> str:
    return moment.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def is_dry_run() -> bool:
    return not DELIVER_FLAG.exists()


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {
        "cursor": format_time(now() - INITIAL_LOOKBACK),
        "consecutive_failures": 0,
        "seen": {},
        "health_reported": {},
    }


def save_state(state: dict) -> None:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    partial = STATE_FILE.with_suffix(".tmp")
    partial.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n")
    partial.replace(STATE_FILE)


def run_in_progress() -> bool:
    if not RUN_LEASE.exists():
        return False
    age = datetime.now(timezone.utc).timestamp() - RUN_LEASE.stat().st_mtime
    return age < RUN_LEASE_TTL.total_seconds()


def release_run() -> None:
    RUN_LEASE.unlink(missing_ok=True)


def excerpt(text: str) -> str:
    return " ".join(text.split())[:EXCERPT_CHARS]


# ---- Linear ----------------------------------------------------------------


def river_email() -> str:
    configured = os.environ.get("PHAGEY_SWEEP_RIVER_EMAIL")
    if configured:
        return configured.lower()
    dotfiles = os.environ.get("PHAGEY_SWEEP_DOTFILES", Path.home() / "dotfiles")
    result = subprocess.run(
        ["git", "-C", str(dotfiles), "config", "user.email"],
        capture_output=True,
        text=True,
    )
    email = result.stdout.strip()
    if result.returncode != 0 or not email:
        raise SweepError(
            f"cannot tell which Linear user is River: git -C {dotfiles} config "
            f"user.email gave nothing and PHAGEY_SWEEP_RIVER_EMAIL is unset"
        )
    return email.lower()


def is_agent_post(body: str) -> bool:
    return AGENT_SIGNATURE in body


def is_relayed_team(issue_identifier: str | None) -> bool:
    return bool(issue_identifier) and issue_identifier.split("-")[0] in RELAYED_TEAMS


def comment_item(comment: dict, source: str) -> dict:
    issue = comment.get("issue_identifier")
    return {
        "key": f"linear:{comment['id']}",
        "source": source,
        "ref": issue or "(project or document comment)",
        "url": comment.get("url") or "n/a",
        "author": (comment.get("user") or {}).get("name") or "River",
        "created_at": comment["created_at"],
        "text": excerpt(comment["body"]),
    }


def linear_items(pages: dict[str, list[dict]], email: str) -> list[dict]:
    """River's unsigned comments worth waking phagey for, each reported once.

    Every comment on the PLT feed counts. A comment on the handle feed counts
    when it carries "phagey:", which also catches project and document comments.
    """
    items: dict[str, dict] = {}
    for feed, source in (("plt", "Linear PLT"), ("handle", f"Linear {HANDLE}")):
        for page in pages[feed]:
            for comment in page["comments"]:
                user = comment.get("user") or {}
                body = comment.get("body") or ""
                if (user.get("email") or "").lower() != email:
                    continue
                if is_agent_post(body):
                    continue
                if is_relayed_team(comment.get("issue_identifier")):
                    continue
                if feed == "handle" and HANDLE not in body.lower():
                    continue
                item = comment_item(comment, source)
                items.setdefault(item["key"], item)
    return list(items.values())


def read_pages() -> dict[str, list[dict]]:
    pages: dict[str, list[dict]] = {}
    for feed in FEEDS:
        files = sorted(PENDING_DIR.glob(f"{feed}-*.json"))
        if not files:
            raise SweepError(f"run ran before the {feed} feed was ingested")
        pages[feed] = [json.loads(path.read_text()) for path in files]
    return pages


def unread_pages_warning(pages: dict[str, list[dict]]) -> list[dict]:
    """A feed whose last page still has more is truncated; say so, don't hide it."""
    return [
        {
            "key": f"truncated:{feed}",
            "source": "sweep",
            "ref": f"{feed} feed",
            "url": "n/a",
            "author": "sweep",
            "created_at": format_time(now()),
            "text": f"The {feed} feed had more pages that were not read; older comments in this window may be missing.",
        }
        for feed, feed_pages in pages.items()
        if feed_pages[-1].get("pagination", {}).get("has_next_page")
    ]


# ---- GitHub ----------------------------------------------------------------


def github_cutoff(cursor: str) -> str:
    return parse_time(cursor).strftime("%Y-%m-%dT%H:%M:%SZ")


def github_items(cursor: str) -> tuple[list[dict], list[str]]:
    """Returns the mentions and a description of anything that went wrong."""
    result = subprocess.run(
        ["timeout", str(GH_TIMEOUT_SECONDS), str(GH_SCRIPT), github_cutoff(cursor)],
        capture_output=True,
        text=True,
    )
    items, problems = [], []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            record = {"kind": "line", "body": line}
        if "error" in record:
            where = record.get("repo") or record.get("kind") or "unknown"
            problems.append(f"{record['error']} ({where}, {record.get('kind', '?')})")
            continue
        items.append(github_item(record))
    if result.returncode != 0:
        reason = (
            "timed out" if result.returncode == 124 else f"exited {result.returncode}"
        )
        problems.append(
            f"gh-phagey-mentions.sh {reason}: {result.stderr.strip()[:200]}"
        )
    return items, problems


def github_item(record: dict) -> dict:
    repo, number = record.get("repo"), record.get("number")
    return {
        "key": f"github:{record.get('kind')}:{record.get('id') or record.get('body', '')[:40]}",
        "source": f"GitHub {record.get('kind', 'mention')}",
        "ref": f"{repo}#{number}" if repo and number else "(unknown)",
        "url": record.get("url") or "n/a",
        "author": "River",
        "created_at": record.get("created_at") or format_time(now()),
        "text": excerpt(record.get("body") or ""),
    }


# ---- Health ----------------------------------------------------------------


def run_quietly(args: list[str], timeout: int, cwd: Path | None = None):
    return subprocess.run(
        args, capture_output=True, text=True, timeout=timeout, cwd=cwd
    )


def min_disk_gib() -> float:
    return float(os.environ.get("PHAGEY_SWEEP_MIN_DISK_GIB", DEFAULT_MIN_DISK_GIB))


def disk_problems() -> dict[str, str]:
    # -k, not -h: the available column is then always a count of 1 KiB blocks.
    result = run_quietly(["df", "-k", DISK_PATH], timeout=30)
    try:
        available_kib = int(result.stdout.strip().splitlines()[-1].split()[3])
    except (IndexError, ValueError):
        return {
            "disk": f"df -k {DISK_PATH} was unreadable: {result.stdout.strip()[:100]}"
        }
    available_gib = available_kib / 1024 / 1024
    if available_gib < min_disk_gib():
        return {
            "disk": f"Only {available_gib:.1f} GiB free on {DISK_PATH} (threshold {min_disk_gib():g} GiB)."
        }
    return {}


REFINERY_STATE = re.compile(r"^\s*State:\s*\S*\s*(\w+)", re.MULTILINE)


def refinery_problems() -> dict[str, str]:
    """The monorepo refinery stays off (phagey's standing rule)."""
    result = run_quietly([GT, "refinery", "status", "monorepo"], timeout=60, cwd=TOWN)
    match = REFINERY_STATE.search(result.stdout)
    if result.returncode != 0 or not match:
        return {
            "refinery": f"The monorepo refinery status was unreadable: {(result.stdout + result.stderr).strip()[:150]}"
        }
    if match.group(1).lower() == "running":
        return {
            "refinery": "The monorepo refinery is running; the standing rule is that it stays off."
        }
    return {}


def delegate_problems() -> dict[str, str]:
    try:
        result = run_quietly([str(DELEGATES_SCRIPT)], timeout=DELEGATES_TIMEOUT_SECONDS)
    except subprocess.TimeoutExpired:
        return {"delegates": "check-delegates.sh timed out."}
    flagged = [line.strip() for line in result.stdout.splitlines() if line.strip()]
    if result.returncode > 1:
        return {
            "delegates": f"check-delegates.sh exited {result.returncode}: {result.stderr.strip()[:150]}"
        }
    return {f"delegate:{line}": f"Delegate check: {line}" for line in flagged}


def health_problems() -> dict[str, str]:
    return {**disk_problems(), **refinery_problems(), **delegate_problems()}


def new_health_items(
    problems: dict[str, str], reported: dict[str, str]
) -> tuple[list[dict], dict]:
    """The problems worth mailing now, and the reported-at record to keep.

    A persisting problem would otherwise mail phagey every 30 minutes.
    """
    items, still_reported = [], {}
    for key, text in problems.items():
        last = reported.get(key)
        if last and now() - parse_time(last) < HEALTH_REMIND_AFTER:
            still_reported[key] = last
            continue
        still_reported[key] = format_time(now())
        items.append(
            {
                "key": f"health:{key}",
                "source": "Health",
                "ref": key.split(":")[0],
                "url": "n/a",
                "author": "sweep",
                "created_at": format_time(now()),
                "text": text,
            }
        )
    return items, still_reported


# ---- Mail ------------------------------------------------------------------


def run_gt(args: list[str]) -> str:
    result = subprocess.run([GT, *args], capture_output=True, text=True, cwd=TOWN)
    if result.returncode != 0:
        raise SweepError(
            f"gt {' '.join(args[:2])} failed ({result.returncode}): {result.stderr.strip()}"
        )
    return result.stdout


def digest(items: list[dict], cursor: str) -> str:
    lines = [f"phagey-sweep found {len(items)} item(s) since {cursor}.", ""]
    for number, item in enumerate(items, start=1):
        lines += [
            f"{number}. {item['source']}: {item['ref']}",
            f"   URL: {item['url']}",
            f"   Author: {item['author']}",
            f"   When: {item['created_at']}",
            f"   {item['text']}",
            "",
        ]
    lines.append(
        "Sent by the phagey-sweep plugin. Answer on the item, not by replying to this mail."
    )
    return "\n".join(lines)


def deliver(subject: str, body: str) -> None:
    if is_dry_run():
        RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
        with DRY_RUN_LOG.open("a") as log:
            log.write(
                f"=== {format_time(now())} WOULD SEND to {PHAGEY}\nSubject: {subject}\n{body}\n\n"
            )
        return
    run_gt(["mail", "send", PHAGEY, "-s", subject, "-m", body])


# ---- Commands --------------------------------------------------------------


def command_begin() -> str:
    RUNTIME_DIR.mkdir(parents=True, exist_ok=True)
    with LOCK_FILE.open("w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if run_in_progress():
            return "BUSY"
        RUN_LEASE.write_text(format_time(now()))
    # Pages left by a failed run must never stand in for this run's reads.
    shutil.rmtree(PENDING_DIR, ignore_errors=True)
    PENDING_DIR.mkdir()
    return f"CURSOR {load_state()['cursor']}"


def command_ingest(feed: str, raw: str) -> str:
    if feed not in FEEDS:
        raise SweepError(f"unknown feed {feed!r}; expected one of {', '.join(FEEDS)}")
    try:
        result = json.loads(raw)
    except json.JSONDecodeError:
        raise SweepError(
            f"{feed} read did not return JSON: {raw.strip()[:200]!r}"
        ) from None
    if not isinstance(result, dict) or not isinstance(result.get("comments"), list):
        # An authorization link or an error message has no comments list.
        raise SweepError(
            f"{feed} read returned no comments list: {raw.strip()[:200]!r}"
        )
    PENDING_DIR.mkdir(parents=True, exist_ok=True)
    pages = len(list(PENDING_DIR.glob(f"{feed}-*.json")))
    (PENDING_DIR / f"{feed}-{pages + 1:02d}.json").write_text(raw)
    return f"ingested {feed} page {pages + 1}: {len(result['comments'])} comment(s)"


def command_run() -> str:
    try:
        return sweep()
    finally:
        release_run()


def sweep() -> str:
    if not RUN_LEASE.exists():
        raise SweepError("run without begin; there is no run lease")
    started = parse_time(RUN_LEASE.read_text().strip())
    pages = read_pages()
    state = load_state()
    cursor = state["cursor"]

    github, github_problems = github_items(cursor)
    health, health_reported = new_health_items(
        health_problems(), state["health_reported"]
    )
    found = linear_items(pages, river_email()) + github + unread_pages_warning(pages)
    found = [item for item in found if item["key"] not in state["seen"]]

    failures = state["consecutive_failures"] + 1 if github_problems else 0
    if failures == FAIL_MAIL_AT:
        found.append(
            failure_item(f"GitHub read failing: {'; '.join(github_problems)}", failures)
        )
    items = found + health

    if items:
        deliver(f"phagey-sweep: {len(items)} items", digest(items, cursor))

    state["consecutive_failures"] = failures
    state["health_reported"] = health_reported
    for item in found:
        state["seen"][item["key"]] = item["created_at"]
    horizon = format_time(now() - SEEN_RETENTION)
    state["seen"] = {k: v for k, v in state["seen"].items() if v >= horizon}
    # A failed GitHub read keeps the cursor, so its window is read again.
    if not github_problems:
        state["cursor"] = max(cursor, format_time(started - CURSOR_OVERLAP))
    save_state(state)

    if not items:
        return "phagey-sweep: nothing to report"
    mode = "logged to dry-run.log" if is_dry_run() else "sent"
    return f"phagey-sweep: {len(items)} item(s) {mode}"


def failure_item(reason: str, failures: int) -> dict:
    return {
        "key": f"failure:{failures}",
        "source": "sweep",
        "ref": "sweep failing",
        "url": "n/a",
        "author": "sweep",
        "created_at": format_time(now()),
        "text": f"{failures} runs in a row have failed. Last: {reason}",
    }


def command_fail(reason: str) -> str:
    release_run()
    state = load_state()
    state["consecutive_failures"] += 1
    failures = state["consecutive_failures"]
    save_state(state)
    if failures == FAIL_MAIL_AT:
        item = failure_item(reason, failures)
        deliver(
            f"phagey-sweep: failing, {failures} runs in a row",
            digest([item], state["cursor"]),
        )
        return f"phagey-sweep: failure {failures} in a row, mailed phagey: {reason}"
    return f"phagey-sweep: failure {failures} in a row: {reason}"


def main(argv: list[str]) -> int:
    command = argv[1] if len(argv) > 1 else ""
    try:
        if command == "begin":
            print(command_begin())
        elif command == "ingest":
            print(command_ingest(argv[2] if len(argv) > 2 else "", sys.stdin.read()))
        elif command == "run":
            print(command_run())
        elif command == "fail":
            print(command_fail(" ".join(argv[2:]) or "unspecified"))
        else:
            print(__doc__, file=sys.stderr)
            return 2
    except Exception as error:
        if command == "fail":
            raise
        print(f"phagey-sweep {command} failed: {error}", file=sys.stderr)
        print(command_fail(f"{command}: {error}"), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
