"""Fixture tests for relay.py. Run: python3 -m unittest discover gastown/plugins/riv-relay"""

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
SIGNATURE = "\\~ Δ Delta, downstream of River"

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
    sent = home / "sent.json"
    messages = json.loads(sent.read_text()) if sent.exists() else []
    if args[:2] == ["mail", "send"]:
        messages.append({"id": f"hq-wisp-{len(messages) + 1}", "to": args[2],
                         "subject": args[args.index("-s") + 1], "timestamp": f"2026-10-21T00:00:{len(messages):02d}Z"})
        sent.write_text(json.dumps(messages))
    elif args[:2] == ["mail", "inbox"]:
        print(json.dumps([m for m in messages if m["to"] == args[2]]))
    """
)


def comment(comment_id, body, created_at="2026-10-21T10:00:00.000Z", parent_id=None):
    return {
        "id": comment_id,
        "body": body,
        "created_at": created_at,
        "parent_id": parent_id,
    }


def issue(
    ident="RIV-9",
    updated_at="2026-10-21T10:00:00.000Z",
    comments=(),
    labels=(),
    description="",
    state=("Todo", "unstarted"),
    completed_at=None,
):
    return {
        "identifier": ident,
        "title": f"Title of {ident}",
        "url": f"https://linear.app/arcadedev/issue/{ident}",
        "updated_at": updated_at,
        "completed_at": completed_at,
        "state": {"name": state[0], "type": state[1]},
        "labels": [{"name": name} for name in labels],
        "description": description,
        "comments": list(comments),
    }


class RelayTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.home = root / "runtime"
        self.gt_home = root / "gt"
        self.gt_home.mkdir()
        fake_gt = root / "gt-bin"
        fake_gt.write_text(FAKE_GT)
        fake_gt.chmod(0o755)
        self.env = {
            "RIV_RELAY_HOME": str(self.home),
            "RIV_RELAY_GT": str(fake_gt),
            "FAKE_GT_HOME": str(self.gt_home),
        }
        os.environ.update(self.env)
        sys.path.insert(0, str(HERE))
        import relay

        self.relay = importlib.reload(relay)

    def tearDown(self):
        sys.path.remove(str(HERE))
        for key in self.env:
            os.environ.pop(key)
        self.tmp.cleanup()

    def deliver_for_real(self):
        self.home.mkdir(parents=True, exist_ok=True)
        (self.home / "DELIVER").touch()

    def run_once(self, *issues):
        """One dog run: check the listing, then relay the issues it asks for."""
        lines = [f"{i['identifier']} {i['updated_at']}" for i in issues]
        answer = self.relay.command_check(lines)
        if answer == "NOTHING_CHANGED":
            return answer
        for item in issues:
            if item["identifier"] in answer.split()[1:]:
                (self.home / "pending" / f"{item['identifier']}.json").write_text(
                    json.dumps({"issue": item})
                )
        return self.relay.command_relay()

    def gt_calls(self):
        calls = self.gt_home / "calls.jsonl"
        return (
            [json.loads(line) for line in calls.read_text().splitlines()]
            if calls.exists()
            else []
        )

    def mails(self):
        return [
            call for call in self.gt_calls() if call["args"][:2] == ["mail", "send"]
        ]

    def subjects(self):
        return [m["args"][m["args"].index("-s") + 1] for m in self.mails()]

    def dry_run_log(self):
        return (self.home / "dry-run.log").read_text()

    def state(self):
        return json.loads((self.home / "state.json").read_text())

    def baseline(self, *issues):
        """Record issues as already read, so later runs relay only what changes."""
        self.deliver_for_real()
        self.run_once(*issues)
        (self.gt_home / "calls.jsonl").unlink(missing_ok=True)


class SignatureAndEdits(RelayTest):
    def test_agent_signed_comments_are_never_relayed(self):
        self.baseline(issue())
        self.run_once(
            issue(
                updated_at="2026-10-21T11:00:00.000Z",
                comments=[
                    comment(
                        "c-agent",
                        f"Picked this up.\n\n{SIGNATURE}",
                        "2026-10-21T10:59:00.000Z",
                    ),
                    comment("c-river", "Ship it.", "2026-10-21T10:59:30.000Z"),
                ],
            )
        )
        self.assertEqual(self.subjects(), ["[RIV-9] River commented: Ship it."])

    def test_an_edit_to_a_relayed_comment_is_relayed_again(self):
        self.baseline(issue())
        first = issue(
            updated_at="2026-10-21T11:00:00.000Z",
            comments=[comment("c1", "Use option A", "2026-10-21T10:59:00.000Z")],
        )
        self.run_once(first)
        edited = issue(
            updated_at="2026-10-21T11:05:00.000Z",
            comments=[comment("c1", "Use option B", "2026-10-21T10:59:00.000Z")],
        )
        self.run_once(edited)
        self.assertEqual(
            self.subjects(),
            [
                "[RIV-9] River commented: Use option A",
                "[RIV-9] River edited a comment: Use option B",
            ],
        )

    def test_subject_carries_the_first_60_characters_on_one_line(self):
        self.baseline(issue())
        body = "Line one\nline two " + "x" * 80
        self.run_once(
            issue(
                updated_at="2026-10-21T11:00:00.000Z",
                comments=[comment("c1", body, "2026-10-21T10:59:00.000Z")],
            )
        )
        self.assertEqual(
            self.subjects(),
            ["[RIV-9] River commented: " + ("Line one line two " + "x" * 80)[:60]],
        )


class Checkboxes(RelayTest):
    BEFORE = "Steps:\n- [ ] Move ML issues\n- [ ] Close PLT-1777"
    AFTER = "Steps:\n- [X] Move ML issues\n- [ ] Close PLT-1777"

    def test_ticks_wait_for_two_identical_reads_then_send_only_the_flips(self):
        self.baseline(issue(labels=["needs-river"], description=self.BEFORE))
        ticked = issue(
            updated_at="2026-10-21T11:00:00.000Z",
            labels=["needs-river"],
            description=self.AFTER,
        )
        self.run_once(ticked)
        self.assertEqual(
            self.mails(), [], "the first read of a change only arms the debounce"
        )
        self.run_once(ticked)
        mail = self.mails()[0]
        self.assertEqual(self.subjects(), ["[RIV-9] River ticked boxes: 1 changed"])
        self.assertIn("[x] Move ML issues", mail["stdin"])
        self.assertNotIn("Close PLT-1777", mail["stdin"])
        self.assertEqual(self.run_once(ticked), "NOTHING_CHANGED")

    def test_a_burst_of_ticks_becomes_one_mail(self):
        self.baseline(issue(labels=["needs-river"], description=self.BEFORE))
        self.run_once(
            issue(
                updated_at="2026-10-21T11:00:00.000Z",
                labels=["needs-river"],
                description=self.AFTER,
            )
        )
        both = self.AFTER.replace("- [ ] Close", "- [X] Close")
        burst = issue(
            updated_at="2026-10-21T11:01:00.000Z",
            labels=["needs-river"],
            description=both,
        )
        self.run_once(burst)
        self.run_once(burst)
        self.assertEqual(self.subjects(), ["[RIV-9] River ticked boxes: 2 changed"])

    def test_description_changes_are_ignored_without_needs_river(self):
        self.baseline(issue(description=self.BEFORE))
        ticked = issue(updated_at="2026-10-21T11:00:00.000Z", description=self.AFTER)
        self.run_once(ticked)
        self.run_once(ticked)
        self.assertEqual(self.mails(), [])


class Routing(RelayTest):
    FOOTER = "Body\n\nAgent: monorepo/crew/phagey\nBead: mo-iprp6b.95"

    def route_of(self, body, labels=(), description=""):
        self.baseline(issue(labels=labels, description=description))
        self.run_once(
            issue(
                updated_at="2026-10-21T11:00:00.000Z",
                labels=labels,
                description=description,
                comments=[comment("c1", body, "2026-10-21T10:59:00.000Z")],
            )
        )
        return self.mails()[-1]

    def test_a_mention_wins_over_label_and_footer(self):
        mail = self.route_of(
            "@gigi please take this", labels=["agent:phagey"], description=self.FOOTER
        )
        self.assertEqual(mail["args"][2], "monorepo/crew/gigi")

    def test_a_label_wins_over_the_footer(self):
        mail = self.route_of(
            "Looks good", labels=["agent:gigi"], description=self.FOOTER
        )
        self.assertEqual(mail["args"][2], "monorepo/crew/gigi")

    def test_the_footer_wins_over_the_default(self):
        mail = self.route_of("Looks good", description=self.FOOTER)
        self.assertEqual(mail["args"][2], "monorepo/crew/phagey")
        self.assertIn("Bead: mo-iprp6b.95", mail["stdin"])

    def test_default_recipient_is_gigi(self):
        mail = self.route_of("Looks good")
        self.assertEqual(mail["args"][2], "monorepo/crew/gigi")
        self.assertIn("Bead: none", mail["stdin"])

    def test_an_email_address_is_not_a_mention(self):
        mail = self.route_of("cc ops@gigi.example", description=self.FOOTER)
        self.assertEqual(mail["args"][2], "monorepo/crew/phagey")

    def test_mail_body_carries_text_url_ids_and_parent(self):
        self.baseline(issue())
        self.run_once(
            issue(
                updated_at="2026-10-21T11:00:00.000Z",
                comments=[
                    comment(
                        "5a57a400-337b",
                        "Full text here",
                        "2026-10-21T10:59:00.000Z",
                        "p-1",
                    )
                ],
            )
        )
        body = self.mails()[0]["stdin"]
        self.assertIn("Full text here", body)
        self.assertIn("https://linear.app/arcadedev/issue/RIV-9#comment-5a57a400", body)
        self.assertIn("Comment ID: 5a57a400-337b", body)
        self.assertIn("Parent comment ID: p-1", body)


class LabelAndStateChanges(RelayTest):
    def test_river_clearing_needs_river_without_a_comment_is_relayed(self):
        self.baseline(issue(labels=["needs-river"]))
        self.run_once(issue(updated_at="2026-10-21T11:00:00.000Z"))
        self.assertEqual(self.subjects(), ["[RIV-9] River cleared needs-river"])

    def test_clearing_after_a_relayed_river_comment_is_not_echoed(self):
        self.baseline(issue(labels=["needs-river"]))
        answered = [comment("c1", "B, go", "2026-10-21T10:59:00.000Z")]
        self.run_once(
            issue(
                updated_at="2026-10-21T11:00:00.000Z",
                labels=["needs-river"],
                comments=answered,
            )
        )
        picked_up = answered + [
            comment("c2", f"On it.\n\n{SIGNATURE}", "2026-10-21T11:02:00.000Z")
        ]
        self.run_once(issue(updated_at="2026-10-21T11:03:00.000Z", comments=picked_up))
        self.assertEqual(self.subjects(), ["[RIV-9] River commented: B, go"])

    def test_moving_to_done_is_relayed_once(self):
        self.baseline(issue())
        done = issue(updated_at="2026-10-21T11:00:00.000Z", state=("Done", "completed"))
        self.run_once(done)
        self.run_once(
            issue(updated_at="2026-10-21T11:05:00.000Z", state=("Done", "completed"))
        )
        self.assertEqual(self.subjects(), ["[RIV-9] River closed it: Done"])


class ClosesByAgents(RelayTest):
    def close_with(self, *comments, state=("Done", "completed"), **fields):
        self.baseline(issue())
        self.run_once(
            issue(
                updated_at="2026-10-21T11:00:00.000Z",
                state=state,
                comments=comments,
                **fields,
            )
        )
        return self.subjects()

    def test_a_close_right_after_an_agent_signed_comment_is_skipped(self):
        signed = comment(
            "c-agent", f"Merged, closing.\n\n{SIGNATURE}", "2026-10-21T10:58:00.000Z"
        )
        self.assertEqual(self.close_with(signed), [])

    def test_river_canceling_without_a_comment_is_relayed(self):
        self.assertEqual(
            self.close_with(state=("Canceled", "canceled")),
            ["[RIV-9] River closed it: Canceled"],
        )

    def test_river_closing_after_her_own_comment_is_relayed(self):
        unsigned = comment("c-river", "Not needed.", "2026-10-21T10:59:00.000Z")
        self.assertEqual(
            self.close_with(unsigned),
            ["[RIV-9] River commented: Not needed.", "[RIV-9] River closed it: Done"],
        )

    def test_a_close_long_after_an_agent_signed_comment_is_relayed(self):
        stale = comment(
            "c-agent", f"Picked this up.\n\n{SIGNATURE}", "2026-10-21T10:30:00.000Z"
        )
        self.assertEqual(self.close_with(stale), ["[RIV-9] River closed it: Done"])

    def test_an_agent_comment_after_river_marked_it_done_is_not_her_close(self):
        reaction = comment(
            "c-agent",
            f"Noted, closing the bead.\n\n{SIGNATURE}",
            "2026-10-21T11:00:00.000Z",
        )
        self.assertEqual(
            self.close_with(reaction, completed_at="2026-10-21T10:57:00.000Z"),
            ["[RIV-9] River closed it: Done"],
        )


class CursorAndChecks(RelayTest):
    def test_nothing_changed_needs_no_fetch(self):
        self.baseline(issue())
        self.assertEqual(
            self.relay.command_check(["RIV-9 2026-10-21T10:00:00.000Z"]),
            "NOTHING_CHANGED",
        )

    def test_a_new_issue_relays_comments_inside_the_cursor_overlap_only(self):
        self.run_once(issue(ident="RIV-1", updated_at="2026-10-21T12:00:00.000Z"))
        self.assertEqual(self.state()["cursor"], "2026-10-21T11:55:00.000Z")
        self.deliver_for_real()
        new_issue = issue(
            ident="RIV-2",
            updated_at="2026-10-21T12:01:00.000Z",
            comments=[
                comment("old", "Before the cursor", "2026-10-21T11:00:00.000Z"),
                comment("new", "Inside the overlap", "2026-10-21T11:58:00.000Z"),
            ],
        )
        self.run_once(
            issue(ident="RIV-1", updated_at="2026-10-21T12:00:00.000Z"), new_issue
        )
        self.assertEqual(
            self.subjects(), ["[RIV-2] River commented: Inside the overlap"]
        )

    def test_issues_read_in_the_same_run_share_one_cursor(self):
        newest_first = [
            issue(ident="RIV-3", updated_at="2026-10-21T12:00:00.000Z"),
            issue(
                ident="RIV-2",
                updated_at="2026-10-19T12:00:00.000Z",
                comments=[comment("c1", "Older issue", "2026-10-19T11:00:00.000Z")],
            ),
        ]
        self.run_once(*newest_first)
        self.assertIn("[RIV-2] River commented: Older issue", self.dry_run_log())

    def test_fresh_delivery_does_not_replay_history(self):
        self.deliver_for_real()
        self.run_once(
            issue(comments=[comment("c1", "Old news", "2026-10-01T00:00:00.000Z")])
        )
        self.assertEqual(self.mails(), [])

    def test_check_rejects_an_empty_listing(self):
        with self.assertRaises(self.relay.RelayError):
            self.relay.command_check([])

    def test_relay_fails_loudly_when_a_requested_snapshot_is_missing(self):
        self.relay.command_check(["RIV-9 2026-10-21T10:00:00.000Z"])
        with self.assertRaises(self.relay.RelayError):
            self.relay.command_relay()


class FetchCap(RelayTest):
    """A run fetches at most RIV_RELAY_MAX_FETCH issues, so a dog never has to
    transcribe a whole backlog in one session."""

    def cap(self, value):
        os.environ["RIV_RELAY_MAX_FETCH"] = str(value)
        self.env["RIV_RELAY_MAX_FETCH"] = str(value)

    def test_check_asks_for_at_most_the_cap_oldest_change_first(self):
        self.cap(2)
        lines = [
            "RIV-3 2026-10-21T12:00:00.000Z",
            "RIV-1 2026-10-21T10:00:00.000Z",
            "RIV-2 2026-10-21T11:00:00.000Z",
        ]
        self.assertEqual(self.relay.command_check(lines), "FETCH RIV-1 RIV-2")

    def test_deferred_issues_hold_the_cursor_and_relay_on_the_next_run(self):
        before = [
            issue(ident=f"RIV-{n}", updated_at=f"2099-01-01T1{n}:00:00.000Z")
            for n in (1, 2, 3)
        ]
        self.baseline(*before)
        cursor = self.state()["cursor"]
        self.cap(2)
        after = [
            issue(
                ident=f"RIV-{n}",
                updated_at=f"2099-01-02T1{n}:00:00.000Z",
                comments=[comment(f"c{n}", f"Note {n}", f"2099-01-02T1{n}:00:00.000Z")],
            )
            for n in (1, 2, 3)
        ]
        self.run_once(*after)
        self.assertEqual(len(self.mails()), 2)
        self.assertEqual(self.state()["cursor"], cursor)
        self.run_once(*after)
        subjects = self.subjects()
        self.assertEqual(len(subjects), 3)
        self.assertEqual(len(set(subjects)), 3)
        self.assertGreater(self.state()["cursor"], cursor)
        self.assertEqual(self.run_once(*after), "NOTHING_CHANGED")


class DeliveryAndFailures(RelayTest):
    def test_dry_run_logs_instead_of_sending_and_replays_history(self):
        self.run_once(
            issue(comments=[comment("c1", "Old news", "2026-10-01T00:00:00.000Z")])
        )
        self.assertEqual(self.gt_calls(), [])
        log = (self.home / "dry-run.log").read_text()
        self.assertIn("WOULD SEND to monorepo/crew/gigi", log)
        self.assertIn("Subject: [RIV-9] River commented: Old news", log)

    def test_flipping_to_delivery_after_a_dry_run_sends_only_new_events(self):
        self.run_once(
            issue(comments=[comment("c1", "Old news", "2026-10-01T00:00:00.000Z")])
        )
        self.deliver_for_real()
        self.run_once(
            issue(
                updated_at="2026-10-21T11:00:00.000Z",
                comments=[
                    comment("c1", "Old news", "2026-10-01T00:00:00.000Z"),
                    comment("c2", "Fresh", "2026-10-21T10:59:00.000Z"),
                ],
            )
        )
        self.assertEqual(self.subjects(), ["[RIV-9] River commented: Fresh"])
        self.assertNotIn(
            "--reply-to",
            self.mails()[0]["args"],
            "a dry-run thread root is not a message ID",
        )

    def test_follow_ups_thread_onto_the_first_mail(self):
        self.baseline(issue())
        first = [comment("c1", "One", "2026-10-21T10:59:00.000Z")]
        self.run_once(issue(updated_at="2026-10-21T11:00:00.000Z", comments=first))
        self.run_once(
            issue(
                updated_at="2026-10-21T11:05:00.000Z",
                comments=first + [comment("c2", "Two", "2026-10-21T11:04:00.000Z")],
            )
        )
        second = self.mails()[1]["args"]
        self.assertEqual(second[second.index("--reply-to") + 1], "hq-wisp-1")

    def test_state_advances_only_after_a_successful_send(self):
        self.baseline(issue())
        changed = issue(
            updated_at="2026-10-21T11:00:00.000Z",
            comments=[comment("c1", "Retry me", "2026-10-21T10:59:00.000Z")],
        )
        (self.gt_home / "FAIL").touch()
        with self.assertRaises(self.relay.RelayError):
            self.run_once(changed)
        self.assertEqual(
            self.state()["issues"]["RIV-9"]["updated_at"], "2026-10-21T10:00:00.000Z"
        )
        (self.gt_home / "FAIL").unlink()
        self.run_once(changed)
        self.assertEqual(self.subjects(), ["[RIV-9] River commented: Retry me"] * 2)

    def test_five_failures_in_a_row_escalate_once(self):
        for _ in range(7):
            self.relay.command_fail("Linear read failed")
        escalations = [
            call["args"] for call in self.gt_calls() if call["args"][0] == "escalate"
        ]
        self.assertEqual(len(escalations), 1)
        self.assertEqual(
            escalations[0][escalations[0].index("--fingerprint") + 1], "riv-relay"
        )

    def test_a_successful_run_resets_the_failure_streak(self):
        for _ in range(4):
            self.relay.command_fail("Linear read failed")
        self.run_once(issue())
        self.assertEqual(self.state()["consecutive_failures"], 0)

    def test_main_counts_an_unexpected_error_as_a_failure(self):
        self.assertEqual(self.relay.main(["relay.py", "relay"]), 1)
        self.assertEqual(self.state()["consecutive_failures"], 1)


if __name__ == "__main__":
    unittest.main()
