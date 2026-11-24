"""Fixture tests for sweep.py. Run: python3 -m unittest discover gastown/plugins/phagey-sweep"""

from __future__ import annotations

import importlib
import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
RIVER = "river@example.test"
SIGNATURE = "\\~ Δ Delta, downstream of River"

FAKE_GT = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    from pathlib import Path
    home = Path(os.environ["FAKE_GT_HOME"])
    args = sys.argv[1:]
    with (home / "calls.jsonl").open("a") as calls:
        calls.write(json.dumps({"args": args}) + "\\n")
    if args[:2] == ["mail", "send"]:
        if (home / "MAIL_FAILS").exists():
            sys.exit("gt mail is down")
    elif args[:2] == ["refinery", "status"]:
        state = (home / "refinery").read_text() if (home / "refinery").exists() else "stopped"
        if state == "garbled":
            print("something unexpected")
        else:
            print(f"Refinery: monorepo\\n\\n  State: {state}\\n\\n  Queue: 0 pending")
    """
)

# The refinery prints a symbol before the state; the fake mimics that.
STOPPED = "○ stopped"
RUNNING = "● running"
GARBLED = "garbled"


def comment(
    comment_id="c1",
    body="Please look at this",
    email=RIVER,
    issue="PLT-7",
    created_at="2026-11-23T10:00:00.000Z",
):
    return {
        "id": comment_id,
        "body": body,
        "created_at": created_at,
        "issue_identifier": issue,
        "url": f"https://linear.example.test/issue/{issue}#comment-{comment_id}",
        "user": {"name": "River", "email": email},
    }


def page(*comments, has_next_page=False):
    return {
        "comments": list(comments),
        "items_returned": len(comments),
        "pagination": {"has_next_page": has_next_page, "end_cursor": "x"},
    }


def mention(number=12, body="phagey: please review", kind="thread"):
    return {
        "kind": kind,
        "repo": "ArcadeAI/monorepo",
        "number": number,
        "id": 900 + number,
        "created_at": "2026-11-23T10:00:00Z",
        "url": f"https://github.example.test/ArcadeAI/monorepo/pull/{number}#c",
        "path": None,
        "line": None,
        "body": body,
    }


class SweepTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "runtime"
        self.gt_home = root / "gt"
        self.gt_home.mkdir()
        self.town = root / "town"
        self.town.mkdir()

        fake_gt = root / "gt-bin"
        fake_gt.write_text(FAKE_GT)
        fake_gt.chmod(0o755)

        self.gh_output = root / "gh-output"
        self.gh_output.write_text("")
        self.gh_calls = root / "gh-calls"
        self.gh_script = self.script(
            root / "gh-mentions.sh",
            f'echo "$@" >> {self.gh_calls}\n'
            f"cat {self.gh_output}\n"
            f"[ -f {root}/GH_FAILS ] && exit 1\nexit 0\n",
        )
        self.delegates_output = root / "delegates-output"
        self.delegates_output.write_text("")
        self.delegates_script = self.script(
            root / "check-delegates.sh",
            f"cat {self.delegates_output}\n"
            f"[ -s {self.delegates_output} ] && exit 1\nexit 0\n",
        )
        self.root = root

        self.env = {
            "PHAGEY_SWEEP_HOME": str(self.home),
            "PHAGEY_SWEEP_GT": str(fake_gt),
            "PHAGEY_SWEEP_TOWN": str(self.town),
            "PHAGEY_SWEEP_GH_SCRIPT": str(self.gh_script),
            "PHAGEY_SWEEP_DELEGATES_SCRIPT": str(self.delegates_script),
            "PHAGEY_SWEEP_RIVER_EMAIL": RIVER,
            "PHAGEY_SWEEP_DISK_PATH": str(root),
            "PHAGEY_SWEEP_MIN_DISK_GIB": "0",
            "FAKE_GT_HOME": str(self.gt_home),
        }
        os.environ.update(self.env)
        sys.path.insert(0, str(HERE))
        import sweep

        self.sweep = importlib.reload(sweep)
        self.set_clock("2026-11-23T10:30:00.000Z")

    def tearDown(self):
        sys.path.remove(str(HERE))
        for key in self.env:
            os.environ.pop(key, None)
        os.environ.pop("PHAGEY_SWEEP_DOTFILES", None)
        self.tmp.cleanup()

    @staticmethod
    def script(path, body):
        path.write_text("#!/bin/bash\n" + body)
        path.chmod(0o755)
        return path

    def set_clock(self, stamp):
        moment = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        self.sweep.now = lambda: moment

    def deliver_for_real(self):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "DELIVER").touch()

    def set_refinery(self, state):
        (self.gt_home / "refinery").write_text(state)

    def set_gh(self, *mentions):
        self.gh_output.write_text("".join(json.dumps(m) + "\n" for m in mentions))

    def sweep_once(self, plt=(), handle=()):
        """One dog run: begin, ingest each feed's pages, run."""
        answer = self.sweep.command_begin()
        if answer == "BUSY":
            return answer
        self.sweep.command_ingest("plt", json.dumps(page(*plt)))
        self.sweep.command_ingest("handle", json.dumps(page(*handle)))
        return self.sweep.command_run()

    def mails(self):
        return [
            call["args"]
            for call in self.gt_calls()
            if call["args"][:2] == ["mail", "send"]
        ]

    def gt_calls(self):
        calls = self.gt_home / "calls.jsonl"
        return (
            [json.loads(line) for line in calls.read_text().splitlines()]
            if calls.exists()
            else []
        )

    def digest(self):
        args = self.mails()[-1]
        return args[args.index("-m") + 1]

    def subject(self):
        args = self.mails()[-1]
        return args[args.index("-s") + 1]

    def state(self):
        return json.loads((self.home / "state.json").read_text())

    def dry_run_log(self):
        return (self.home / "dry-run.log").read_text()


class LinearFiltering(SweepTest):
    def test_keeps_rivers_comment_on_plt(self):
        self.deliver_for_real()
        self.sweep_once(plt=[comment(body="Can you chase this?")])
        self.assertEqual(self.subject(), "phagey-sweep: 1 items")
        self.assertIn("PLT-7", self.digest())
        self.assertIn("Can you chase this?", self.digest())

    def test_drops_other_peoples_comments(self):
        self.deliver_for_real()
        self.sweep_once(plt=[comment(email="evan@example.test")])
        self.assertEqual(self.mails(), [])

    def test_email_match_ignores_case(self):
        self.deliver_for_real()
        self.sweep_once(plt=[comment(email=RIVER.upper())])
        self.assertEqual(len(self.mails()), 1)

    def test_drops_agent_signed_comments_in_both_escaped_forms(self):
        self.deliver_for_real()
        self.sweep_once(
            plt=[
                comment("c1", "Done.\n\n~ Δ Delta, downstream of River"),
                comment("c2", "Done.\n\n" + SIGNATURE),
            ]
        )
        self.assertEqual(self.mails(), [])

    def test_handle_feed_keeps_phagey_colon_comments_outside_plt(self):
        self.deliver_for_real()
        self.sweep_once(handle=[comment("c9", "phagey: check the doc", issue=None)])
        self.assertIn("phagey: check the doc", self.digest())
        self.assertIn("project or document comment", self.digest())

    def test_handle_feed_drops_comments_without_the_handle(self):
        self.deliver_for_real()
        self.sweep_once(handle=[comment("c9", "just a note", issue="TOO-5")])
        self.assertEqual(self.mails(), [])

    def test_handle_match_ignores_case(self):
        self.deliver_for_real()
        self.sweep_once(handle=[comment("c9", "Phagey: hi", issue="TOO-5")])
        self.assertEqual(len(self.mails()), 1)

    def test_never_duplicates_riv(self):
        # riv-relay already carries RIV; a "phagey:" there must not mail twice.
        self.deliver_for_real()
        self.sweep_once(
            plt=[comment("c1", "on RIV", issue="RIV-130")],
            handle=[comment("c2", "phagey: do both", issue="RIV-130")],
        )
        self.assertEqual(self.mails(), [])

    def test_a_comment_in_both_feeds_is_one_item(self):
        self.deliver_for_real()
        both = comment("c1", "phagey: look at PLT-7")
        self.sweep_once(plt=[both], handle=[both])
        self.assertEqual(self.subject(), "phagey-sweep: 1 items")

    def test_digest_carries_source_issue_url_author_and_300_characters(self):
        self.deliver_for_real()
        self.sweep_once(plt=[comment(body="x" * 500)])
        digest = self.digest()
        self.assertIn("Linear PLT", digest)
        self.assertIn("PLT-7", digest)
        self.assertIn("https://linear.example.test/issue/PLT-7#comment-c1", digest)
        self.assertIn("Author: River", digest)
        self.assertIn("x" * 300, digest)
        self.assertNotIn("x" * 301, digest)

    def test_unexpected_user_shape_is_dropped_not_crashed(self):
        self.deliver_for_real()
        broken = comment()
        broken["user"] = None
        self.sweep_once(plt=[broken])
        self.assertEqual(self.mails(), [])


class RiverEmail(SweepTest):
    def test_falls_back_to_the_dotfiles_git_email(self):
        os.environ.pop("PHAGEY_SWEEP_RIVER_EMAIL")
        repo = self.root / "dotfiles"
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        subprocess.run(
            ["git", "-C", str(repo), "config", "user.email", "git@example.test"],
            check=True,
        )
        os.environ["PHAGEY_SWEEP_DOTFILES"] = str(repo)
        self.deliver_for_real()
        self.sweep_once(plt=[comment(email="git@example.test")])
        self.assertEqual(len(self.mails()), 1)

    def test_an_unreadable_email_is_a_failure_not_silence(self):
        os.environ.pop("PHAGEY_SWEEP_RIVER_EMAIL")
        os.environ["PHAGEY_SWEEP_DOTFILES"] = str(self.root / "no-such-repo")
        self.sweep.command_begin()
        self.sweep.command_ingest("plt", json.dumps(page()))
        self.sweep.command_ingest("handle", json.dumps(page()))
        with self.assertRaises(self.sweep.SweepError):
            self.sweep.command_run()


class GitHubMentions(SweepTest):
    def test_each_output_line_is_a_mention(self):
        self.deliver_for_real()
        self.set_gh(mention(12), mention(13, "phagey: second"))
        self.sweep_once()
        digest = self.digest()
        self.assertEqual(self.subject(), "phagey-sweep: 2 items")
        self.assertIn("GitHub thread", digest)
        self.assertIn("ArcadeAI/monorepo#12", digest)
        self.assertIn("https://github.example.test/ArcadeAI/monorepo/pull/12#c", digest)
        self.assertIn("phagey: second", digest)

    def test_script_gets_the_cursor_as_a_second_precision_cutoff(self):
        self.sweep_once()
        # first run looks back 24h from the clock, 2026-11-23T10:30:00Z
        self.assertEqual(self.gh_calls.read_text().strip(), "2026-11-22T10:30:00Z")

    def test_a_line_that_is_not_json_is_still_a_mention(self):
        self.deliver_for_real()
        self.gh_output.write_text("something odd\n")
        self.sweep_once()
        self.assertIn("something odd", self.digest())

    def test_a_fetch_error_line_holds_the_cursor_and_is_not_a_mention(self):
        self.deliver_for_real()
        self.sweep_once()
        cursor = self.state()["cursor"]
        self.gh_output.write_text(
            json.dumps(
                {"error": "fetch failed", "repo": "ArcadeAI/mlops", "kind": "thread"}
            )
            + "\n"
        )
        self.set_clock("2026-11-23T11:30:00.000Z")
        self.sweep_once()
        self.assertEqual(self.mails(), [])
        self.assertEqual(self.state()["cursor"], cursor)
        self.assertEqual(self.state()["consecutive_failures"], 1)

    def test_a_failing_script_holds_the_cursor(self):
        self.deliver_for_real()
        self.sweep_once()
        cursor = self.state()["cursor"]
        (self.root / "GH_FAILS").touch()
        self.set_clock("2026-11-23T11:30:00.000Z")
        self.sweep_once()
        self.assertEqual(self.state()["cursor"], cursor)
        self.assertEqual(self.state()["consecutive_failures"], 1)

    def test_third_github_failure_in_a_row_mails_phagey(self):
        self.deliver_for_real()
        (self.root / "GH_FAILS").touch()
        for minute in ("10:30", "11:00", "11:30"):
            self.set_clock(f"2026-11-23T{minute}:00.000Z")
            self.sweep_once()
        self.assertEqual(len(self.mails()), 1)
        self.assertIn("GitHub", self.digest())
        self.assertIn("3 runs in a row", self.digest())

    def test_mentions_are_not_resent_while_the_cursor_is_held(self):
        self.deliver_for_real()
        self.set_gh(mention(12))
        (self.root / "GH_FAILS").touch()
        self.sweep_once()
        self.sweep_once()
        self.assertEqual(len(self.mails()), 1)


class Health(SweepTest):
    def test_low_disk_is_an_item(self):
        self.deliver_for_real()
        os.environ["PHAGEY_SWEEP_MIN_DISK_GIB"] = "100000000"
        self.sweep_once()
        self.assertIn("disk", self.digest().lower())
        self.assertIn("GiB", self.digest())

    def test_plenty_of_disk_is_silent(self):
        self.deliver_for_real()
        self.sweep_once()
        self.assertEqual(self.mails(), [])

    def test_a_running_monorepo_refinery_is_an_item(self):
        self.deliver_for_real()
        self.set_refinery(RUNNING)
        self.sweep_once()
        self.assertIn("refinery", self.digest().lower())

    def test_a_stopped_refinery_is_silent(self):
        self.deliver_for_real()
        self.set_refinery(STOPPED)
        self.sweep_once()
        self.assertEqual(self.mails(), [])

    def test_unreadable_refinery_status_is_an_item(self):
        self.deliver_for_real()
        self.set_refinery(GARBLED)
        self.sweep_once()
        self.assertIn("refinery", self.digest().lower())
        self.assertIn("unreadable", self.digest().lower())

    def test_flagged_delegates_are_items(self):
        self.deliver_for_real()
        self.delegates_output.write_text(
            "DOWN gs/crew/drummer\nPROMPT dotfiles/crew/marsha\n"
        )
        self.sweep_once()
        self.assertIn("DOWN gs/crew/drummer", self.digest())
        self.assertIn("PROMPT dotfiles/crew/marsha", self.digest())
        self.assertEqual(self.subject(), "phagey-sweep: 2 items")

    def test_a_health_problem_is_mailed_once_then_reminded_after_six_hours(self):
        self.deliver_for_real()
        self.set_refinery(RUNNING)
        self.sweep_once()
        self.set_clock("2026-11-23T11:00:00.000Z")
        self.sweep_once()
        self.assertEqual(len(self.mails()), 1)
        self.set_clock("2026-11-23T16:31:00.000Z")
        self.sweep_once()
        self.assertEqual(len(self.mails()), 2)

    def test_a_cleared_problem_is_mailed_again_if_it_returns(self):
        self.deliver_for_real()
        self.set_refinery(RUNNING)
        self.sweep_once()
        self.set_refinery(STOPPED)
        self.sweep_once()
        self.set_refinery(RUNNING)
        self.sweep_once()
        self.assertEqual(len(self.mails()), 2)


class Cursor(SweepTest):
    def test_first_run_looks_back_a_day(self):
        self.assertEqual(self.sweep.command_begin(), "CURSOR 2026-11-22T10:30:00.000Z")

    def test_cursor_advances_to_run_start_minus_overlap(self):
        self.deliver_for_real()
        self.sweep_once()
        self.assertEqual(self.state()["cursor"], "2026-11-23T10:25:00.000Z")
        self.assertEqual(self.sweep.command_begin(), "CURSOR 2026-11-23T10:25:00.000Z")

    def test_cursor_never_moves_backwards(self):
        self.deliver_for_real()
        self.sweep_once()
        self.set_clock("2026-11-23T10:00:00.000Z")
        self.sweep_once()
        self.assertEqual(self.state()["cursor"], "2026-11-23T10:25:00.000Z")

    def test_overlap_does_not_resend_a_comment_already_mailed(self):
        self.deliver_for_real()
        again = comment("c1")
        self.sweep_once(plt=[again])
        self.set_clock("2026-11-23T11:00:00.000Z")
        self.sweep_once(plt=[again])
        self.assertEqual(len(self.mails()), 1)

    def test_a_failed_send_keeps_the_cursor_and_retries_the_item(self):
        self.deliver_for_real()
        (self.gt_home / "MAIL_FAILS").touch()
        with self.assertRaises(self.sweep.SweepError):
            self.sweep_once(plt=[comment()])
        self.assertFalse((self.home / "state.json").exists())
        (self.gt_home / "MAIL_FAILS").unlink()
        self.sweep_once(plt=[comment()])
        self.assertIn("PLT-7", self.digest())

    def test_seen_ids_are_pruned_after_a_week(self):
        self.deliver_for_real()
        self.sweep_once(plt=[comment("old")])
        self.set_clock("2026-12-01T10:30:00.000Z")
        self.sweep_once()
        self.assertEqual(self.state()["seen"], {})


class DeliveryGate(SweepTest):
    def test_without_deliver_nothing_is_sent_and_the_digest_is_logged(self):
        self.sweep_once(plt=[comment(body="Please look")])
        self.assertEqual(self.mails(), [])
        log = self.dry_run_log()
        self.assertIn("WOULD SEND to monorepo/crew/phagey", log)
        self.assertIn("Subject: phagey-sweep: 1 items", log)
        self.assertIn("Please look", log)

    def test_dry_run_still_advances_state(self):
        self.sweep_once(plt=[comment()])
        self.assertEqual(self.state()["cursor"], "2026-11-23T10:25:00.000Z")

    def test_with_deliver_one_mail_goes_to_phagey(self):
        self.deliver_for_real()
        self.set_gh(mention())
        self.sweep_once(plt=[comment()])
        self.assertEqual(len(self.mails()), 1)
        self.assertEqual(self.mails()[0][2], "monorepo/crew/phagey")

    def test_nothing_found_sends_nothing_and_logs_nothing(self):
        self.sweep_once()
        self.assertEqual(self.mails(), [])
        self.assertFalse((self.home / "dry-run.log").exists())

    def test_summary_line_counts_items(self):
        self.assertEqual(
            self.sweep_once(plt=[comment()]),
            "phagey-sweep: 1 item(s) logged to dry-run.log",
        )
        self.deliver_for_real()
        self.assertEqual(
            self.sweep_once(plt=[comment("c2")]), "phagey-sweep: 1 item(s) sent"
        )
        self.assertEqual(self.sweep_once(), "phagey-sweep: nothing to report")


class Robustness(SweepTest):
    def test_overlapping_run_is_told_busy(self):
        self.sweep.command_begin()
        self.assertEqual(self.sweep.command_begin(), "BUSY")

    def test_a_dead_runs_lease_expires(self):
        self.sweep.command_begin()
        # the lease's age is its file mtime, so age the file rather than the clock
        lease = self.home / "run.lease"
        old = lease.stat().st_mtime - 3600
        os.utime(lease, (old, old))
        self.assertTrue(self.sweep.command_begin().startswith("CURSOR"))

    def test_run_releases_the_lease(self):
        self.sweep_once()
        self.assertTrue(self.sweep.command_begin().startswith("CURSOR"))

    def test_run_without_both_feeds_fails_loudly(self):
        self.sweep.command_begin()
        self.sweep.command_ingest("plt", json.dumps(page()))
        with self.assertRaises(self.sweep.SweepError):
            self.sweep.command_run()

    def test_an_auth_link_instead_of_comments_is_rejected(self):
        self.sweep.command_begin()
        with self.assertRaises(self.sweep.SweepError):
            self.sweep.command_ingest(
                "plt", json.dumps({"authorization_url": "https://example.test/auth"})
            )

    def test_non_json_is_rejected(self):
        self.sweep.command_begin()
        with self.assertRaises(self.sweep.SweepError):
            self.sweep.command_ingest("plt", "Please sign in at https://example.test")

    def test_unknown_feed_is_rejected(self):
        self.sweep.command_begin()
        with self.assertRaises(self.sweep.SweepError):
            self.sweep.command_ingest("rubbish", json.dumps(page()))

    def test_extra_pages_are_all_read(self):
        self.deliver_for_real()
        self.sweep.command_begin()
        self.sweep.command_ingest(
            "plt", json.dumps(page(comment("c1"), has_next_page=True))
        )
        self.sweep.command_ingest("plt", json.dumps(page(comment("c2"))))
        self.sweep.command_ingest("handle", json.dumps(page()))
        self.sweep.command_run()
        self.assertEqual(self.subject(), "phagey-sweep: 2 items")

    def test_stopping_with_more_pages_available_is_flagged_not_hidden(self):
        self.deliver_for_real()
        self.sweep.command_begin()
        self.sweep.command_ingest(
            "plt", json.dumps(page(comment("c1"), has_next_page=True))
        )
        self.sweep.command_ingest("handle", json.dumps(page()))
        self.sweep.command_run()
        self.assertIn("not read", self.digest())

    def test_fail_counts_and_stays_quiet_until_the_third(self):
        self.deliver_for_real()
        self.sweep.command_fail("plt read: boom")
        self.sweep.command_fail("plt read: boom")
        self.assertEqual(self.mails(), [])
        self.assertEqual(self.state()["consecutive_failures"], 2)

    def test_third_consecutive_failure_mails_phagey_with_the_reason(self):
        self.deliver_for_real()
        for _ in range(3):
            self.sweep.command_fail("plt read: needs authorization")
        self.assertEqual(len(self.mails()), 1)
        self.assertEqual(self.mails()[0][2], "monorepo/crew/phagey")
        self.assertIn("3 runs in a row", self.subject())
        self.assertIn("plt read: needs authorization", self.digest())

    def test_a_fourth_failure_does_not_mail_again(self):
        self.deliver_for_real()
        for _ in range(4):
            self.sweep.command_fail("boom")
        self.assertEqual(len(self.mails()), 1)

    def failure_mails(self):
        return [m for m in self.mails() if "failing" in m[m.index("-s") + 1]]

    def test_a_failure_mail_that_fails_to_send_is_retried_on_the_next_failure(self):
        # The outage being reported can take mail down too; one lost send must not
        # silence the whole streak.
        self.deliver_for_real()
        self.sweep.command_fail("boom")
        self.sweep.command_fail("boom")
        (self.gt_home / "MAIL_FAILS").touch()
        with self.assertRaises(self.sweep.SweepError):
            self.sweep.command_fail("boom")
        (self.gt_home / "MAIL_FAILS").unlink()
        self.sweep.command_fail("boom")
        self.assertEqual(len(self.failure_mails()), 2)
        self.assertIn("4 runs in a row", self.subject())

    def test_a_new_failure_streak_mails_again(self):
        self.deliver_for_real()
        for _ in range(3):
            self.sweep.command_fail("boom")
        self.sweep_once()
        for _ in range(3):
            self.sweep.command_fail("boom")
        self.assertEqual(len(self.failure_mails()), 2)

    def test_a_good_run_resets_the_failure_count(self):
        self.sweep.command_fail("boom")
        self.sweep.command_fail("boom")
        self.sweep_once()
        self.assertEqual(self.state()["consecutive_failures"], 0)

    def test_fail_releases_the_lease(self):
        self.sweep.command_begin()
        self.sweep.command_fail("boom")
        self.assertTrue(self.sweep.command_begin().startswith("CURSOR"))

    def test_main_counts_a_rejected_ingest_as_a_failure(self):
        self.sweep.command_begin()
        sys.stdin = __import__("io").StringIO("not json")
        try:
            code = self.sweep.main(["sweep.py", "ingest", "plt"])
        finally:
            sys.stdin = sys.__stdin__
        self.assertEqual(code, 1)
        self.assertEqual(self.state()["consecutive_failures"], 1)


if __name__ == "__main__":
    unittest.main()
