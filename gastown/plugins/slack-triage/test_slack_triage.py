"""Fixture tests for slack_triage.py. Run: python3 -m unittest discover gastown/plugins/slack-triage"""

from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
import textwrap
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
NEEDS_RIVER = "66b00900-266c-4e29-986a-8498b980185b"
AGENT_PHAGEY = "8360f084-000f-4827-8ffa-49b1cbaebada"
SLACK = "ff6aa6d3-cfa0-4257-b345-5621dd29d0c6"
THREAD_ROOT = "https://arcade-ai.slack.com/archives/C09GKFHN015/p1793304730964829"
IN_THREAD = (
    THREAD_ROOT.replace("4730964829", "4924931039") + "?thread_ts=1793304730.964829"
)
LATER_IN_THREAD = (
    THREAD_ROOT.replace("4730964829", "5001000001") + "?thread_ts=1793304730.964829"
)
DM = "https://arcade-ai.slack.com/archives/D0A79E4CE4U/p1793483242385439"

FAKE_GT = textwrap.dedent(
    """\
    #!/usr/bin/env python3
    import json, os, sys
    from pathlib import Path
    with (Path(os.environ["FAKE_GT_HOME"]) / "calls.jsonl").open("a") as calls:
        calls.write(json.dumps(sys.argv[1:]) + "\\n")
    """
)


def ask(source=IN_THREAD, **overrides):
    item = {
        "kind": "ask",
        "source": source,
        "title": "Reply to Guru: include Sterling in the on-prem discussions",
        "why": "Guru asked you directly in #proj-tool-recommendation.",
        "ask": "Confirm you'll include Sterling.",
        "default": "Guru assumes Sterling is out of the loop.",
        "refs": ["RIV-45"],
        "suggested_reply": "Will do. Adding Sterling to the next sync.",
    }
    item.update(overrides)
    return item


class SlackTriageTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "runtime"
        self.gt_home = root / "gt"
        self.gt_home.mkdir()
        gt_bin = root / "gt-bin"
        gt_bin.write_text(FAKE_GT)
        gt_bin.chmod(0o755)
        self.env = {
            "SLACK_TRIAGE_HOME": str(self.home),
            "SLACK_TRIAGE_GT": str(gt_bin),
            "FAKE_GT_HOME": str(self.gt_home),
        }
        os.environ.update(self.env)
        sys.path.insert(0, str(HERE))
        import slack_triage

        self.triage = importlib.reload(slack_triage)
        self.clock = datetime(2026, 10, 30, 3, 0, tzinfo=timezone.utc)
        self.triage.now = lambda: self.clock
        self.linear = []
        self.next_riv = 50

    def tearDown(self):
        sys.path.remove(str(HERE))
        for key in self.env:
            os.environ.pop(key)
        self.tmp.cleanup()

    def deliver_for_real(self):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "DELIVER").touch()

    def linear_result(self, call):
        inputs = call["inputs"]
        if call["tool_name"] == "Linear.CreateIssue":
            riv = f"RIV-{self.next_riv}"
            self.next_riv += 1
            return {"issue": {"identifier": riv}, "created": True}
        if call["tool_name"] == "Linear.AddComment":
            return {"id": "cmt-1", "issue_identifier": inputs["issue"]}
        return {"issue": {"identifier": inputs["issue_id"]}, "updated": True}

    def run_once(self, items, fail_at=None):
        """One dog run: begin, plan the items, make each printed call, then apply."""
        window = self.triage.command_begin()
        if window == "BUSY":
            return window
        answer = self.triage.command_plan(json.dumps(items))
        if not answer.startswith("CALLS"):
            return answer
        for line in answer.splitlines()[1:]:
            _, call_id, payload = line.split(" ", 2)
            call = json.loads(payload)
            if call_id == fail_at:
                return self.triage.command_apply(f"{call_id} failed")
            self.linear.append(call)
            (self.home / "pending" / f"{call_id}.json").write_text(
                json.dumps(self.linear_result(call))
            )
        return self.triage.command_apply("")

    def state(self):
        return json.loads((self.home / "state.json").read_text())

    def tools(self):
        return [call["tool_name"] for call in self.linear]

    def test_first_window_starts_where_web_stopped(self):
        self.assertEqual(
            self.triage.command_begin(),
            "WINDOW 2026-10-29T23:05:00Z 2026-10-30T03:00:00Z",
        )

    def test_window_is_capped_so_one_run_never_reads_days_of_slack(self):
        self.clock = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
        self.assertEqual(
            self.triage.command_begin(),
            "WINDOW 2026-10-29T23:05:00Z 2026-10-30T11:05:00Z",
        )

    def test_empty_run_advances_the_window(self):
        self.assertIn("nothing new", self.run_once([]))
        self.assertEqual(self.state()["window_start"], "2026-10-30T03:00:00Z")
        self.assertFalse((self.home / "run.lease").exists())

    def test_second_run_is_busy_while_the_first_holds_the_lease(self):
        self.triage.command_begin()
        self.assertEqual(self.triage.command_begin(), "BUSY")

    def test_stale_lease_from_a_dead_dog_is_taken_over(self):
        self.triage.command_begin()
        self.clock += timedelta(minutes=21)
        self.assertTrue(self.triage.command_begin().startswith("WINDOW"))

    def test_dry_run_logs_the_issue_and_makes_no_calls(self):
        answer = self.run_once([ask()])
        self.assertTrue(answer.startswith("DONE slack-triage (dry-run): 1 item(s)"))
        self.assertEqual(self.linear, [])
        log = (self.home / "dry-run.log").read_text()
        self.assertIn("Linear.CreateIssue", log)
        self.assertEqual(self.state()["threads"], {})
        self.assertEqual(self.state()["window_start"], "2026-10-30T03:00:00Z")

    def test_ask_files_a_signed_todo_issue_for_river(self):
        self.deliver_for_real()
        self.assertEqual(
            self.run_once([ask()]),
            "slack-triage: 1 issue(s) filed, 0 comment(s) for 2026-10-29T23:05:00Z..2026-10-30T03:00:00Z",
        )
        inputs = self.linear[0]["inputs"]
        self.assertEqual(inputs["team"], "RIV")
        self.assertEqual(inputs["state"], "Todo")
        self.assertEqual(inputs["assignee"], "river@arcade.dev")
        self.assertEqual(inputs["labels_to_add"], [NEEDS_RIVER, AGENT_PHAGEY, SLACK])
        body = inputs["description"]
        for part in (
            "**Why:**",
            "**Ask:**",
            "**Default:**",
            "> Will do.",
            f"- Slack: {IN_THREAD}",
            "- RIV-45",
            "`@phagey send`",
        ):
            self.assertIn(part, body)
        self.assertTrue(body.endswith("~ Δ Delta, downstream of River"))

    def test_fyi_and_optional_titles_get_their_prefix_once(self):
        self.deliver_for_real()
        self.run_once(
            [
                ask(kind="fyi", source=DM, title="Engine OOM repro in staging"),
                ask(kind="optional", title="Optional: weigh in on the DPA wording"),
            ]
        )
        titles = [call["inputs"]["title"] for call in self.linear]
        self.assertEqual(
            titles,
            [
                "FYI: Engine OOM repro in staging",
                "Optional: weigh in on the DPA wording",
            ],
        )

    def test_new_message_in_a_tracked_thread_comments_and_reflags(self):
        self.deliver_for_real()
        self.run_once([ask()])
        self.linear.clear()
        self.run_once([ask(source=LATER_IN_THREAD, ask="Answer Guru's follow-up.")])
        self.assertEqual(self.tools(), ["Linear.AddComment", "Linear.UpdateIssue"])
        self.assertEqual(self.linear[0]["inputs"]["issue"], "RIV-50")
        self.assertIn("New in the Slack thread", self.linear[0]["inputs"]["body"])
        self.assertEqual(
            self.linear[1]["inputs"],
            {"issue_id": "RIV-50", "state": "Todo", "labels_to_add": [NEEDS_RIVER]},
        )

    def test_already_handled_message_is_skipped(self):
        self.deliver_for_real()
        self.run_once([ask()])
        self.linear.clear()
        self.assertIn("nothing new", self.run_once([ask()]))
        self.assertEqual(self.linear, [])

    def test_answer_is_relayed_into_the_named_issue_only(self):
        self.deliver_for_real()
        answer = {
            "kind": "answer",
            "source": DM,
            "issue": "RIV-12",
            "quote": "Org creator is whoever ran signup.\nNot the billing owner.",
            "summary": "Shub says the org creator is the signup user.",
        }
        self.run_once([answer])
        self.assertEqual(self.tools(), ["Linear.AddComment"])
        body = self.linear[0]["inputs"]["body"]
        self.assertIn(
            "> Org creator is whoever ran signup.\n> Not the billing owner.", body
        )
        self.assertEqual(self.state()["threads"], {})

    def test_failed_call_keeps_the_window_and_skips_what_succeeded_on_retry(self):
        self.deliver_for_real()
        with self.assertRaises(self.triage.SlackTriageError):
            self.run_once(
                [ask(), ask(kind="fyi", source=DM, title="Staging OOM")], fail_at="c2"
            )
        self.assertEqual(self.state()["window_start"], "2026-10-29T23:05:00Z")
        self.triage.command_fail("c2 failed")
        self.linear.clear()
        self.run_once([ask(), ask(kind="fyi", source=DM, title="Staging OOM")])
        self.assertEqual(self.tools(), ["Linear.CreateIssue"])
        self.assertEqual(self.linear[0]["inputs"]["title"], "FYI: Staging OOM")

    def test_bad_items_are_rejected_with_the_reason(self):
        self.triage.command_begin()
        cases = [
            ([{"kind": "rant", "source": DM}], "kind must be one of"),
            ([ask(why="")], "missing why"),
            ([ask(source="https://example.com/x")], "not a Slack message permalink"),
            ([ask(), ask(source=LATER_IN_THREAD)], "two items for one Slack thread"),
            (
                [
                    {
                        "kind": "answer",
                        "source": DM,
                        "issue": "TOO-1",
                        "quote": "q",
                        "summary": "s",
                    }
                ],
                "RIV-12",
            ),
        ]
        for items, message in cases:
            with (
                self.subTest(message=message),
                self.assertRaisesRegex(self.triage.SlackTriageError, message),
            ):
                self.triage.command_plan(json.dumps(items))

    def test_fifth_failure_escalates_once(self):
        for _ in range(5):
            self.triage.command_fail("gateway down")
        calls = (self.gt_home / "calls.jsonl").read_text().splitlines()
        self.assertEqual(len(calls), 1)
        self.assertIn("slack-triage", json.loads(calls[0]))


if __name__ == "__main__":
    unittest.main()
