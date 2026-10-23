"""Fixture tests for review_inbox.py. Run: python3 -m unittest discover gastown/plugins/review-inbox"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
RIVER = "itsthatriver"
KEY = "ArcadeAI/monorepo#5766"
NEEDS_RIVER = "66b00900-266c-4e29-986a-8498b980185b"

FAKE_GH = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    from pathlib import Path
    home = Path(os.environ["FAKE_GH_HOME"])
    args = sys.argv[1:]
    with (home / "calls.jsonl").open("a") as calls:
        calls.write(json.dumps(args) + "\\n")
    if (home / "FAIL").exists():
        sys.exit("gh: API rate limit exceeded")
    if args[:2] == ["search", "prs"]:
        print((home / "search.json").read_text())
    elif args[:2] == ["api", "graphql"]:
        fields = dict(a.split("=", 1) for a in args if "=" in a and not a.startswith("query="))
        name = f"{fields['owner']}_{fields['name']}_{fields['number']}.json"
        print((home / "prs" / name).read_text())
    """
)

FAKE_GT = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    from pathlib import Path
    home = Path(os.environ["FAKE_GT_HOME"])
    args = sys.argv[1:]
    body = sys.stdin.read() if "--stdin" in args else None
    with (home / "calls.jsonl").open("a") as calls:
        calls.write(json.dumps({"args": args, "stdin": body}) + "\\n")
    if (home / "FAIL").exists():
        sys.exit("gt is down")
    """
)


def review(review_id, state="APPROVED", commit="h1"):
    return {
        "id": review_id,
        "state": state,
        "submittedAt": f"2026-10-22T12:00:0{review_id[-1]}Z",
        "author": {"login": RIVER},
        "commit": {"oid": commit},
    }


def pull(
    key=KEY,
    title="feat(engine): central multi-profile status read",
    state="OPEN",
    additions=40,
    deletions=5,
    labels=("app:engine",),
    requested=True,
    as_code_owner=False,
    reviews=(),
    head="h1",
    body="Closes [TOO-2654](https://linear.app/x)\n\n## What/why\n\nReads every profile at once.\nSo the dashboard stops polling.\nThird line.",
):
    repo, number = key.split("#")
    requests = [{"asCodeOwner": True, "requestedReviewer": {}}]
    if requested:
        requests.append(
            {"asCodeOwner": as_code_owner, "requestedReviewer": {"login": RIVER}}
        )
    return {
        "key": key,
        "search": state == "OPEN" and requested,
        "data": {
            "viewer": {"login": RIVER},
            "repository": {
                "pullRequest": {
                    "title": title,
                    "url": f"https://github.com/{repo}/pull/{number}",
                    "state": state,
                    "body": body,
                    "additions": additions,
                    "deletions": deletions,
                    "changedFiles": 3,
                    "headRefOid": head,
                    "author": {"login": "byrro"},
                    "labels": {"nodes": [{"name": name} for name in labels]},
                    "reviewRequests": {"nodes": requests},
                    "reviews": {
                        "nodes": [
                            {
                                "id": "bot",
                                "state": "COMMENTED",
                                "submittedAt": "2026-10-22T13:00:00Z",
                                "author": {"login": "cursor"},
                                "commit": {"oid": head},
                            },
                            *reviews,
                        ]
                    },
                }
            },
        },
    }


class ReviewInboxTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "runtime"
        self.gh_home = root / "gh"
        self.gt_home = root / "gt"
        (self.gh_home / "prs").mkdir(parents=True)
        self.gt_home.mkdir()
        binaries = {}
        for name, script in (("gh", FAKE_GH), ("gt", FAKE_GT)):
            binaries[name] = root / f"{name}-bin"
            binaries[name].write_text(script)
            binaries[name].chmod(0o755)
        self.env = {
            "REVIEW_INBOX_HOME": str(self.home),
            "REVIEW_INBOX_GH": str(binaries["gh"]),
            "REVIEW_INBOX_GT": str(binaries["gt"]),
            "FAKE_GH_HOME": str(self.gh_home),
            "FAKE_GT_HOME": str(self.gt_home),
        }
        os.environ.update(self.env)
        sys.path.insert(0, str(HERE))
        import review_inbox

        self.inbox = importlib.reload(review_inbox)
        self.linear = []
        self.next_riv = 12
        self.github()

    def tearDown(self):
        sys.path.remove(str(HERE))
        for key in self.env:
            os.environ.pop(key)
        self.tmp.cleanup()

    def github(self, *prs):
        """Set what GitHub returns: the search lists the PRs still requesting River."""
        search = []
        for pr in prs:
            repo, number = pr["key"].split("#")
            name = f"{repo.replace('/', '_')}_{number}.json"
            (self.gh_home / "prs" / name).write_text(json.dumps({"data": pr["data"]}))
            if pr["search"]:
                search.append(
                    {
                        "repository": {"nameWithOwner": repo},
                        "number": int(number),
                        "title": pr["data"]["repository"]["pullRequest"]["title"],
                        "url": pr["data"]["repository"]["pullRequest"]["url"],
                    }
                )
        (self.gh_home / "search.json").write_text(json.dumps(search))

    def deliver_for_real(self):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "DELIVER").touch()

    def linear_result(self, call):
        inputs = call["inputs"]
        if call["tool_name"] == "Linear.CreateIssue":
            riv = f"RIV-{self.next_riv}"
            self.next_riv += 1
            return {
                "issue": {
                    "identifier": riv,
                    "url": f"https://linear.app/arcadedev/issue/{riv}",
                },
                "created": True,
            }
        if call["tool_name"] == "Linear.AddComment":
            return {
                "id": "cmt-1",
                "issue_identifier": inputs["issue"],
                "body": inputs["body"],
            }
        return {"issue": {"identifier": inputs["issue_id"]}, "updated": True}

    def run_once(self, fail_at=None):
        """One dog run: check, make each printed call, then apply."""
        answer = self.inbox.command_check()
        if not answer.startswith("CALLS"):
            return answer
        for line in answer.splitlines()[1:]:
            _, call_id, payload = line.split(" ", 2)
            call = json.loads(payload)
            if call_id == fail_at:
                return self.inbox.command_apply(f"{call_id} failed")
            self.linear.append(call)
            (self.home / "pending" / f"{call_id}.json").write_text(
                json.dumps(self.linear_result(call))
            )
        return self.inbox.command_apply("")

    def tracked(self, pr, **kwargs):
        """Deliver mode with the PR's issue already created, and calls forgotten."""
        self.deliver_for_real()
        self.github(pr)
        self.run_once(**kwargs)
        self.linear.clear()
        (self.gt_home / "calls.jsonl").unlink(missing_ok=True)

    def tools(self):
        return [call["tool_name"] for call in self.linear]

    def mails(self):
        calls = self.gt_home / "calls.jsonl"
        if not calls.exists():
            return []
        return [
            call
            for call in map(json.loads, calls.read_text().splitlines())
            if call["args"][:2] == ["mail", "send"]
        ]

    def gt_calls(self):
        calls = self.gt_home / "calls.jsonl"
        return (
            [json.loads(line) for line in calls.read_text().splitlines()]
            if calls.exists()
            else []
        )

    def state(self):
        return json.loads((self.home / "state.json").read_text())

    def record(self, key=KEY):
        return self.state()["prs"][key]


class NewRequests(ReviewInboxTest):
    def test_a_new_request_creates_one_riv_issue_with_every_field(self):
        self.deliver_for_real()
        self.github(pull(labels=("risk:medium",)))
        self.run_once()
        self.assertEqual(self.tools(), ["Linear.CreateIssue"])
        inputs = self.linear[0]["inputs"]
        self.assertEqual(
            {k: v for k, v in inputs.items() if k != "description"},
            {
                "team": "RIV",
                "title": "Review: #5766 feat(engine): central multi-profile status read",
                "state": "Todo",
                "labels_to_add": [NEEDS_RIVER],
                "assignee": "river@arcade.dev",
            },
        )
        description = inputs["description"]
        for expected in (
            "@byrro",
            "+40 / -5 across 3 file(s)",
            "risk:medium",
            "direct request, added manually",
            "[ArcadeAI/monorepo#5766](https://github.com/ArcadeAI/monorepo/pull/5766)",
            "> Reads every profile at once.\n> So the dashboard stops polling.",
        ):
            self.assertIn(expected, description)
        self.assertNotIn("Third line", description)
        self.assertNotIn("Closes", description)
        self.assertTrue(description.endswith("~ Δ Delta, downstream of River"))
        self.assertEqual(self.record()["riv"], "RIV-12")

    def test_the_summary_skips_template_lines_and_marks_truncation(self):
        body = (
            "<!--\ninstructions\n-->\nLinear ticket: [change_me]\nPart of TOO-1\n"
            + "y" * 250
        )
        lines = self.inbox.summary_lines(body)
        self.assertEqual(lines, ["y" * 199 + "…"])
        self.assertEqual(self.inbox.summary_lines(""), ["(The PR has no description.)"])

    def test_the_same_pr_twice_makes_one_issue(self):
        self.deliver_for_real()
        self.github(pull())
        self.run_once()
        self.assertEqual(self.run_once(), "NOTHING_CHANGED")
        self.assertEqual(self.tools(), ["Linear.CreateIssue"])

    def test_a_codeowner_request_says_so(self):
        self.deliver_for_real()
        self.github(pull(as_code_owner=True))
        self.run_once()
        self.assertIn("as a CODEOWNER", self.linear[0]["inputs"]["description"])

    def test_the_search_asks_only_for_direct_requests(self):
        self.run_once()
        searches = [
            args
            for args in map(
                json.loads, (self.gh_home / "calls.jsonl").read_text().splitlines()
            )
            if args[:2] == ["search", "prs"]
        ]
        self.assertIn("user-review-requested:@me", searches[0])
        self.assertIn("--state=open", searches[0])

    def test_nothing_changed_reads_only_the_search(self):
        self.tracked(pull())
        (self.gh_home / "calls.jsonl").unlink()
        self.assertEqual(self.run_once(), "NOTHING_CHANGED")
        gh_calls = (self.gh_home / "calls.jsonl").read_text().splitlines()
        self.assertEqual(len(gh_calls), 1)


class PreliminaryReviewMail(ReviewInboxTest):
    def mail_for(self, **kwargs):
        self.deliver_for_real()
        self.github(pull(**kwargs))
        self.run_once()
        return self.mails()

    def test_over_500_changed_lines_mails_gigi_with_both_links(self):
        mails = self.mail_for(additions=400, deletions=101)
        self.assertEqual(len(mails), 1)
        self.assertEqual(mails[0]["args"][2], "monorepo/crew/gigi")
        self.assertIn(
            "https://github.com/ArcadeAI/monorepo/pull/5766", mails[0]["stdin"]
        )
        self.assertIn("https://linear.app/arcadedev/issue/RIV-12", mails[0]["stdin"])
        self.assertIn("501 changed lines", mails[0]["stdin"])

    def test_exactly_500_changed_lines_sends_no_mail(self):
        self.assertEqual(self.mail_for(additions=400, deletions=100), [])

    def test_risk_high_mails_gigi_even_when_small(self):
        mails = self.mail_for(labels=("risk:high",))
        self.assertIn("the risk:high label", mails[0]["stdin"])

    def test_the_mail_is_sent_once(self):
        self.mail_for(labels=("risk:high",))
        self.run_once()
        self.assertEqual(len(self.mails()), 1)

    def test_a_failed_mail_is_retried_without_recreating_the_issue(self):
        (self.gt_home / "FAIL").touch()
        self.deliver_for_real()
        self.github(pull(labels=("risk:high",)))
        with self.assertRaises(self.inbox.ReviewInboxError):
            self.run_once()
        self.assertEqual(self.record()["riv"], "RIV-12")
        (self.gt_home / "FAIL").unlink()
        self.run_once()
        self.assertEqual(self.tools(), ["Linear.CreateIssue"])
        self.assertEqual(len(self.mails()), 2, "one failed send, one retry")


class Transitions(ReviewInboxTest):
    def assert_comment_then(self, update, phrase):
        self.assertEqual(self.tools(), ["Linear.AddComment", "Linear.UpdateIssue"])
        comment, change = (call["inputs"] for call in self.linear)
        self.assertEqual(comment["issue"], "RIV-12")
        self.assertIn(phrase, comment["body"])
        self.assertTrue(comment["body"].endswith("~ Δ Delta, downstream of River"))
        self.assertEqual(change, {"issue_id": "RIV-12", **update})

    def test_a_withdrawn_request_comments_then_moves_to_done(self):
        self.tracked(pull())
        self.github(pull(requested=False))
        self.run_once()
        self.assert_comment_then({"state": "Done"}, "was withdrawn")

    def test_a_merged_pr_comments_then_moves_to_done(self):
        self.tracked(pull())
        self.github(pull(state="MERGED"))
        self.run_once()
        self.assert_comment_then({"state": "Done"}, "was merged")

    def test_a_closed_pr_comments_then_moves_to_done(self):
        self.tracked(pull())
        self.github(pull(state="CLOSED"))
        self.run_once()
        self.assert_comment_then({"state": "Done"}, "closed without merging")

    def test_river_reviewing_comments_then_moves_to_done(self):
        self.tracked(pull())
        self.github(pull(requested=False, reviews=[review("r1", "CHANGES_REQUESTED")]))
        self.run_once()
        self.assert_comment_then(
            {"state": "Done"}, "submitted a review (changes requested)"
        )

    def test_an_older_review_from_before_the_request_does_not_count(self):
        self.tracked(pull(reviews=[review("r1")]))
        self.github(pull(requested=False, reviews=[review("r1")]))
        self.run_once()
        self.assert_comment_then({"state": "Done"}, "was withdrawn")

    def test_search_lag_is_not_a_withdrawal(self):
        self.tracked(pull())
        lagging = pull()
        lagging["search"] = False
        self.github(lagging)
        self.assertEqual(self.run_once(), "NOTHING_CHANGED")
        self.assertEqual(self.linear, [])

    def test_new_commits_after_her_review_flag_needs_river_once(self):
        self.tracked(pull())
        self.github(pull(requested=False, reviews=[review("r1", commit="h1")]))
        self.run_once()
        self.linear.clear()
        pushed = pull(requested=False, reviews=[review("r1", commit="h1")], head="h2")
        self.github(pushed)
        self.run_once()
        self.assert_comment_then({"labels_to_add": [NEEDS_RIVER]}, "head h2")
        self.linear.clear()
        self.assertEqual(self.run_once(), "NOTHING_CHANGED")

    def test_no_new_commits_after_her_review_is_quiet(self):
        self.tracked(pull())
        self.github(pull(requested=False, reviews=[review("r1")]))
        self.run_once()
        self.linear.clear()
        self.assertEqual(self.run_once(), "NOTHING_CHANGED")

    def test_reviewing_the_new_commits_moves_it_back_to_done(self):
        self.tracked(pull())
        self.github(pull(requested=False, reviews=[review("r1", commit="h1")]))
        self.run_once()
        self.github(
            pull(requested=False, reviews=[review("r1", commit="h1")], head="h2")
        )
        self.run_once()
        self.linear.clear()
        self.github(
            pull(requested=False, reviews=[review("r2", commit="h2")], head="h2")
        )
        self.run_once()
        self.assert_comment_then({"state": "Done"}, "submitted a review (approved)")

    def test_being_asked_again_after_a_review_flags_needs_river(self):
        self.tracked(pull())
        self.github(pull(requested=False, reviews=[review("r1")]))
        self.run_once()
        self.linear.clear()
        self.github(pull(reviews=[review("r1")]))
        self.run_once()
        self.assert_comment_then({"labels_to_add": [NEEDS_RIVER]}, "requested again")

    def test_being_asked_again_after_new_commits_were_flagged_writes_nothing(self):
        self.tracked(pull())
        self.github(pull(requested=False, reviews=[review("r1", commit="h1")]))
        self.run_once()
        self.github(
            pull(requested=False, reviews=[review("r1", commit="h1")], head="h2")
        )
        self.run_once()
        self.linear.clear()
        self.github(pull(reviews=[review("r1", commit="h1")], head="h2"))
        self.assertIn("no Linear writes", self.run_once())
        self.assertEqual(self.linear, [])
        self.assertEqual(self.record()["phase"], "requested")

    def test_a_merged_pr_is_never_read_again(self):
        self.tracked(pull())
        self.github(pull(state="MERGED"))
        self.run_once()
        (self.gh_home / "calls.jsonl").unlink()
        self.assertEqual(self.run_once(), "NOTHING_CHANGED")
        self.assertEqual(
            len((self.gh_home / "calls.jsonl").read_text().splitlines()), 1
        )


class DryRun(ReviewInboxTest):
    def test_dry_run_logs_the_writes_and_mail_and_performs_none(self):
        self.github(pull(labels=("risk:high",)))
        answer = self.run_once()
        self.assertTrue(
            answer.startswith("DONE review-inbox: 1 Linear write(s) and 1 mail(s)")
        )
        self.assertEqual(self.linear, [], "the dog is given no calls to make")
        self.assertEqual(self.gt_calls(), [], "gt is never called")
        log = (self.home / "dry-run.log").read_text()
        self.assertIn(
            "WOULD CALL Linear.CreateIssue for ArcadeAI/monorepo#5766 (create)", log
        )
        self.assertIn('"title": "Review: #5766', log)
        self.assertIn("WOULD SEND to monorepo/crew/gigi", log)

    def test_dry_run_records_progress_so_each_write_is_logged_once(self):
        self.github(pull())
        self.run_once()
        self.assertEqual(self.run_once(), "NOTHING_CHANGED")
        self.github(pull(state="MERGED"))
        self.assertIn("2 Linear write(s)", self.run_once())
        log = (self.home / "dry-run.log").read_text()
        self.assertIn('"issue": "dry-run"', log)
        self.assertEqual(self.gt_calls(), [])

    def test_turning_on_delivery_creates_real_issues_for_open_requests(self):
        self.github(pull(), pull(key="ArcadeAI/monorepo#4646"))
        self.run_once()
        self.github(pull())
        self.run_once()
        self.deliver_for_real()
        self.run_once()
        self.assertEqual(self.tools(), ["Linear.CreateIssue"])
        self.assertEqual(self.record()["riv"], "RIV-12")


class FailuresAndRetries(ReviewInboxTest):
    def test_a_failed_update_retries_only_that_call(self):
        self.tracked(pull())
        self.github(pull(state="MERGED"))
        with self.assertRaises(self.inbox.ReviewInboxError):
            self.run_once(fail_at="c2")
        self.assertEqual(self.tools(), ["Linear.AddComment"])
        self.assertEqual(self.record()["phase"], "requested")
        self.run_once()
        self.assertEqual(self.tools(), ["Linear.AddComment", "Linear.UpdateIssue"])
        self.assertEqual(self.record()["phase"], "closed")

    def test_a_failed_create_is_retried_next_run(self):
        self.deliver_for_real()
        self.github(pull())
        with self.assertRaises(self.inbox.ReviewInboxError):
            self.run_once(fail_at="c1")
        self.run_once()
        self.assertEqual(self.tools(), ["Linear.CreateIssue"])
        self.assertEqual(self.record()["riv"], "RIV-12")

    def test_a_result_that_is_not_a_success_counts_as_a_failure(self):
        self.deliver_for_real()
        self.github(pull())
        self.inbox.command_check()
        (self.home / "pending" / "c1.json").write_text(
            json.dumps({"error": "Team 'RIV' not found", "suggestions": ["RIVER"]})
        )
        with self.assertRaises(self.inbox.ReviewInboxError):
            self.inbox.command_apply("")
        self.assertNotIn(KEY, self.state()["prs"])

    def test_a_github_failure_counts_through_main(self):
        (self.gh_home / "FAIL").touch()
        self.assertEqual(self.inbox.main(["review_inbox.py", "check"]), 1)
        self.assertEqual(self.state()["consecutive_failures"], 1)

    def test_five_failures_in_a_row_escalate_once(self):
        for _ in range(7):
            self.inbox.command_fail("Linear write failed")
        escalations = [c["args"] for c in self.gt_calls() if c["args"][0] == "escalate"]
        self.assertEqual(len(escalations), 1)
        self.assertEqual(
            escalations[0][escalations[0].index("--fingerprint") + 1], "review-inbox"
        )

    def test_a_clean_run_resets_the_failure_streak(self):
        for _ in range(4):
            self.inbox.command_fail("Linear write failed")
        self.run_once()
        self.assertEqual(self.state()["consecutive_failures"], 0)

    def test_apply_without_a_plan_fails_loudly(self):
        with self.assertRaises(self.inbox.ReviewInboxError):
            self.inbox.command_apply("")


if __name__ == "__main__":
    unittest.main()
