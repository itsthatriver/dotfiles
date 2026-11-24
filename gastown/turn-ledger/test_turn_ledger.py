"""Fixture tests for the turn ledger. Run: python3 -m unittest discover gastown/turn-ledger"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import goals  # noqa: E402
import turn_ledger  # noqa: E402

SCRIPT = HERE / "turn_ledger.py"
SESSION = "11111111-2222-3333-4444-555555555555"
CREW_CWD = str(Path.home() / "gt/dotfiles/crew/marsha")


class GoalClassifierTests(unittest.TestCase):
    def classify(self, prompt, sigtok=None, flags=""):
        return goals.classify(prompt, sigtok or {}, flags)

    def test_sweep_prompt_is_high_confidence_monitoring(self):
        result = self.classify(
            "RIV + GitHub sweep: poll everything", {"edit_code": 900}
        )
        self.assertEqual(result, ("monitoring", "P06_sweep_poll", "high", ""))

    def test_compaction_flag_is_overhead_even_without_prompt_text(self):
        result = self.classify("", {}, flags="isCompactSummary")
        self.assertEqual(result, ("overhead", "P01_compaction", "high", ""))

    def test_dog_plugin_dispatch_maps_plugin_to_goal(self):
        result = self.classify("Plugin dolt-backup dispatched to you")
        self.assertEqual(
            result, ("maintenance", "P08_dog_plugin", "high", "dolt-backup")
        )

    def test_unknown_plugin_is_low_confidence_other(self):
        result = self.classify("Plugin mystery dispatched")
        self.assertEqual(result, ("other", "P08_dog_plugin", "low", "mystery"))

    def test_plugin_mail_records_plugin_name_as_subtype(self):
        result = self.classify(
            "📬 You have new mail from daemon. Subject: Plugin: riv-relay failed"
        )
        self.assertEqual(result, ("management", "P07_plugin_mail", "high", "riv-relay"))

    def test_review_prompt_is_review(self):
        self.assertEqual(
            self.classify("please review this change")[:2], ("review", "P11_review")
        )

    def test_message_prompt_defers_to_tool_profile(self):
        goal, rule, confidence, _ = self.classify("📬 hello", {"edit_code": 1000})
        self.assertEqual(
            (goal, rule, confidence), ("implementation", "P13_message+tools", "high")
        )

    def test_message_prompt_without_tools_falls_back_with_low_confidence(self):
        result = self.classify("📬 hello")
        self.assertEqual(result, ("management", "P13_message+fallback", "low", ""))

    def test_no_prompt_uses_tools_with_low_confidence(self):
        result = self.classify("", {"mail": 500})
        self.assertEqual(result, ("management", "P00_no_prompt", "low", ""))

    def test_tools_only_is_high_confidence_when_one_group_exceeds_sixty_percent(self):
        result = self.classify("fix the thing", {"edit_code": 700, "mail": 300})
        self.assertEqual(result, ("implementation", "T1_tools", "high", ""))

    def test_tools_only_is_low_confidence_when_no_group_exceeds_sixty_percent(self):
        result = self.classify("fix the thing", {"mail": 500, "ci_poll": 500})
        self.assertEqual(result[2], "low")

    def test_tool_calls_that_cost_no_tokens_cannot_vote(self):
        result = self.classify("fix the thing", {"edit_code": 0, "read": 0})
        self.assertEqual(result, ("other", "T2_nothing", "low", ""))

    def test_nothing_to_go_on_is_other(self):
        result = self.classify("fix the thing")
        self.assertEqual(result, ("other", "T2_nothing", "low", ""))

    def test_bash_signatures(self):
        cases = {
            "make test": "test",
            "gt mail send foo": "mail",
            "gh pr checks 12": "ci_poll",
            "git commit -m x": "git_write",
            "git rebase main": "upkeep",
            "ls -la": "explore",
            "frobnicate": "bash_other",
        }
        for command, expected in cases.items():
            with self.subTest(command=command):
                self.assertEqual(goals.signature("Bash", command), expected)

    def test_non_bash_signatures(self):
        self.assertEqual(goals.signature("Edit", "src/app.py"), "edit_code")
        self.assertEqual(goals.signature("Write", "notes.md"), "edit_doc")
        self.assertEqual(goals.signature("Agent", "do a thing"), "delegate")
        self.assertEqual(goals.signature("Arcade:Linear.AddComment", "{}"), "comment")
        self.assertEqual(goals.signature("Arcade:Linear.ListIssues", "{}"), "poll_read")
        self.assertEqual(goals.signature("TodoWrite", ""), "neutral")


def at(minute, second=0, hour=10):
    return f"2026-11-24T{hour:02d}:{minute:02d}:{second:02d}.000Z"


class Transcript:
    """Builds a Claude transcript fixture one record at a time."""

    def __init__(self, path, session_id=SESSION, cwd=CREW_CWD, sidechain=False):
        self.path = Path(path)
        self.session_id = session_id
        self.cwd = cwd
        self.sidechain = sidechain
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.touch()

    def write(self, record):
        record.setdefault("sessionId", self.session_id)
        record.setdefault("cwd", self.cwd)
        with self.path.open("a") as handle:
            handle.write(json.dumps(record) + "\n")

    def user(self, text, timestamp, prompt_id=None, origin="human", **extra):
        content = text if isinstance(text, (str, list)) else str(text)
        self.write(
            {
                "type": "user",
                "isSidechain": False,
                "promptId": prompt_id,
                "origin": {"kind": origin},
                "message": {"role": "user", "content": content},
                "timestamp": timestamp,
                **extra,
            }
        )

    def tool_result(self, timestamp):
        block = {"type": "tool_result", "tool_use_id": "toolu_1", "content": "ok"}
        self.write(
            {
                "type": "user",
                "isSidechain": False,
                "message": {"role": "user", "content": [block]},
                "timestamp": timestamp,
            }
        )

    def assistant(
        self,
        message_id,
        timestamp,
        stop_reason="end_turn",
        model="claude-opus-5-5",
        tools=(),
        **usage,
    ):
        fields = {"input_tokens": 0, "output_tokens": 0}
        fields.update(usage)
        content = [{"type": "text", "text": "ok"}]
        content += [
            {"type": "tool_use", "id": tool_id, "name": name, "input": tool_input}
            for tool_id, name, tool_input in tools
        ]
        self.write(
            {
                "type": "assistant",
                "isSidechain": self.sidechain,
                "requestId": "req_" + message_id,
                "message": {
                    "id": message_id,
                    "model": model,
                    "role": "assistant",
                    "content": content,
                    "stop_reason": stop_reason,
                    "usage": fields,
                },
                "timestamp": timestamp,
            }
        )


class LedgerTestCase(unittest.TestCase):
    def setUp(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        self.root = Path(scratch.name)
        self.home = self.root / "ledger"
        self.transcript = Transcript(self.root / "projects/proj" / f"{SESSION}.jsonl")

    def ingest(self, event="Stop", cwd=CREW_CWD, session_id=SESSION):
        hook_input = {
            "hook_event_name": event,
            "session_id": session_id,
            "transcript_path": str(self.transcript.path),
            "cwd": cwd,
        }
        return turn_ledger.ingest(self.home, "claude", hook_input)

    def records(self):
        lines = []
        for ledger_file in sorted(self.home.glob("????-??-??.jsonl")):
            lines += ledger_file.read_text().splitlines()
        return [json.loads(line) for line in lines]

    def simple_turn(self, prompt, start_minute, message_id, **usage):
        self.transcript.user(prompt, at(start_minute))
        self.transcript.assistant(message_id, at(start_minute, 5), **usage)


class SingleTurnTests(LedgerTestCase):
    def test_one_complete_turn_becomes_one_record_with_exact_tokens(self):
        self.simple_turn(
            "fix the bug",
            0,
            "msg_1",
            input_tokens=1000,
            output_tokens=500,
            cache_read_input_tokens=4000,
            cache_creation_input_tokens=2000,
        )
        self.ingest()
        (record,) = self.records()
        self.assertEqual(record["agent"], "claude")
        self.assertEqual(record["session_id"], SESSION)
        self.assertEqual(record["ts_start"], at(0))
        self.assertEqual(record["ts_end"], at(0, 5))
        self.assertEqual(
            record["models"],
            {
                "claude-opus-5-5": {
                    "input": 1000,
                    "output": 500,
                    "cache_write_5m": 2000,
                    "cache_write_1h": 0,
                    "cache_read": 4000,
                }
            },
        )
        self.assertEqual(record["api_calls"], 1)
        self.assertEqual(record["ctx_max"], 7000)
        expected_usd = (1000 * 4.00 + 500 * 20.00 + 2000 * 5.00 + 4000 * 0.20) / 1e6
        self.assertAlmostEqual(record["usd_equiv"], expected_usd)

    def test_cache_creation_breakdown_splits_5m_and_1h(self):
        self.transcript.user("go", at(0))
        self.transcript.assistant(
            "msg_1",
            at(0, 5),
            cache_creation_input_tokens=300,
            cache_creation={
                "ephemeral_5m_input_tokens": 100,
                "ephemeral_1h_input_tokens": 200,
            },
        )
        self.ingest()
        (record,) = self.records()
        tokens = record["models"]["claude-opus-5-5"]
        self.assertEqual(
            (tokens["cache_write_5m"], tokens["cache_write_1h"]), (100, 200)
        )

    def test_missing_cache_creation_breakdown_counts_as_5m(self):
        self.transcript.user("go", at(0))
        self.transcript.assistant("msg_1", at(0, 5), cache_creation_input_tokens=300)
        self.ingest()
        tokens = self.records()[0]["models"]["claude-opus-5-5"]
        self.assertEqual((tokens["cache_write_5m"], tokens["cache_write_1h"]), (300, 0))

    def test_tokens_are_split_per_model(self):
        self.transcript.user("go", at(0))
        self.transcript.assistant("msg_1", at(0, 5), input_tokens=10)
        self.transcript.assistant(
            "msg_2", at(0, 9), model="claude-haiku-4-5-20251001", input_tokens=7
        )
        self.ingest()
        models = self.records()[0]["models"]
        self.assertEqual(models["claude-opus-5-5"]["input"], 10)
        self.assertEqual(models["claude-haiku-4-5-20251001"]["input"], 7)

    def test_prompt_text_stays_out_of_the_record_except_an_80_char_head(self):
        secret = "hunter2 " * 30
        self.simple_turn(secret, 0, "msg_1")
        self.ingest()
        (record,) = self.records()
        self.assertEqual(record["prompt_head"], secret[:80])
        self.assertNotIn(secret.strip(), json.dumps(record))

    def test_text_block_prompts_start_turns_too(self):
        self.transcript.user([{"type": "text", "text": "hello there"}], at(0))
        self.transcript.assistant("msg_1", at(0, 5))
        self.ingest()
        self.assertEqual(self.records()[0]["prompt_head"], "hello there")


class TurnBoundaryTests(LedgerTestCase):
    def test_two_turns_are_caught_up_in_one_invocation(self):
        self.simple_turn("first", 0, "msg_1", output_tokens=1)
        self.simple_turn("second", 10, "msg_2", output_tokens=2)
        self.ingest()
        first, second = self.records()
        self.assertEqual(
            (first["prompt_head"], second["prompt_head"]), ("first", "second")
        )
        self.assertEqual(first["models"]["claude-opus-5-5"]["output"], 1)
        self.assertEqual(second["models"]["claude-opus-5-5"]["output"], 2)

    def test_streaming_duplicates_are_deduped_by_message_id(self):
        self.transcript.user("go", at(0))
        for second, output in ((1, 5), (2, 40), (3, 90)):
            self.transcript.assistant(
                "msg_1", at(0, second), input_tokens=3, output_tokens=output
            )
        self.ingest()
        (record,) = self.records()
        tokens = record["models"]["claude-opus-5-5"]
        self.assertEqual((tokens["input"], tokens["output"]), (3, 90))
        self.assertEqual(record["api_calls"], 1)

    def test_tool_result_records_do_not_start_a_turn(self):
        self.transcript.user("go", at(0))
        self.transcript.assistant(
            "msg_1", at(0, 5), stop_reason="tool_use", output_tokens=1
        )
        self.transcript.tool_result(at(0, 6))
        self.transcript.assistant("msg_2", at(0, 9), output_tokens=2)
        self.ingest()
        (record,) = self.records()
        self.assertEqual(record["models"]["claude-opus-5-5"]["output"], 3)
        self.assertEqual(record["api_calls"], 2)

    def test_final_turn_ending_in_tool_use_stays_open_until_it_finishes(self):
        self.simple_turn("first", 0, "msg_1")
        self.transcript.user("second", at(10))
        self.transcript.assistant(
            "msg_2", at(10, 5), stop_reason="tool_use", output_tokens=1
        )
        self.ingest()
        self.assertEqual([r["prompt_head"] for r in self.records()], ["first"])

        self.transcript.tool_result(at(10, 6))
        self.transcript.assistant("msg_3", at(10, 9), output_tokens=2)
        self.ingest()
        records = self.records()
        self.assertEqual([r["prompt_head"] for r in records], ["first", "second"])
        self.assertEqual(records[1]["models"]["claude-opus-5-5"]["output"], 3)

    def test_session_end_flushes_an_open_turn(self):
        self.transcript.user("go", at(0))
        self.transcript.assistant(
            "msg_1", at(0, 5), stop_reason="tool_use", output_tokens=4
        )
        self.ingest("Stop")
        self.assertEqual(self.records(), [])
        self.ingest("SessionEnd")
        (record,) = self.records()
        self.assertEqual(record["models"]["claude-opus-5-5"]["output"], 4)

    def test_turn_with_no_assistant_reply_yet_stays_open(self):
        self.transcript.user("go", at(0))
        self.ingest()
        self.assertEqual(self.records(), [])

    def test_rerunning_on_the_same_transcript_adds_nothing(self):
        self.simple_turn("first", 0, "msg_1")
        self.simple_turn("second", 10, "msg_2")
        self.ingest()
        self.ingest()
        self.ingest("SessionEnd")
        self.assertEqual(len(self.records()), 2)

    def test_a_half_written_trailing_line_is_left_for_the_next_run(self):
        self.simple_turn("first", 0, "msg_1")
        self.transcript.user("second", at(10))
        with self.transcript.path.open("a") as handle:
            handle.write('{"type": "assistant", "message": {"id": "msg_2", "usa')
        self.ingest()
        self.assertEqual(len(self.records()), 1)

    def test_records_land_in_a_file_named_for_the_utc_date_of_turn_end(self):
        self.transcript.user("late", "2026-11-24T23:59:50.000Z")
        self.transcript.assistant("msg_1", "2026-11-25T00:00:10.000Z")
        self.ingest()
        self.assertTrue((self.home / "2026-11-25.jsonl").exists())
        self.assertFalse((self.home / "2026-11-24.jsonl").exists())

    def test_transcript_that_shrinks_restarts_from_the_top_and_logs_it(self):
        self.simple_turn("first" + " padding" * 100, 0, "msg_1")
        self.ingest()
        self.transcript.path.write_text("")
        self.simple_turn("again", 20, "msg_9")
        self.ingest()
        self.assertEqual(
            [r["prompt_head"][:5] for r in self.records()], ["first", "again"]
        )
        self.assertIn("smaller than its cursor", (self.home / "errors.log").read_text())


class ColdCallTests(LedgerTestCase):
    def test_calls_more_than_five_minutes_after_the_previous_one_are_cold(self):
        self.transcript.user("go", at(0))
        self.transcript.assistant("msg_1", at(0, 5), stop_reason="tool_use")
        self.transcript.assistant("msg_2", at(2, 0), stop_reason="tool_use")
        self.transcript.assistant("msg_3", at(8, 0), stop_reason="tool_use")
        self.transcript.assistant("msg_4", at(13, 1))
        self.ingest()
        (record,) = self.records()
        self.assertEqual(record["api_calls"], 4)
        self.assertEqual(record["cold_calls"], 2)

    def test_a_calls_gap_is_measured_from_the_previous_turns_last_call(self):
        self.simple_turn("first", 0, "msg_1")
        self.simple_turn("second", 3, "msg_2")
        self.simple_turn("third", 30, "msg_3")
        self.ingest()
        self.assertEqual([r["cold_calls"] for r in self.records()], [0, 0, 1])

    def test_the_previous_call_is_remembered_between_invocations(self):
        self.simple_turn("first", 0, "msg_1")
        self.ingest()
        self.simple_turn("second", 30, "msg_2")
        self.ingest()
        self.assertEqual([r["cold_calls"] for r in self.records()], [0, 1])


class SubagentTests(LedgerTestCase):
    def subagent_file(self, name="agent-a1"):
        directory = self.transcript.path.parent / SESSION / "subagents"
        return Transcript(directory / f"{name}.jsonl", sidechain=True)

    def test_subagent_usage_is_attributed_by_the_turns_time_window(self):
        self.simple_turn("first", 0, "msg_1", output_tokens=1)
        self.simple_turn("second", 10, "msg_2", output_tokens=2)
        sub = self.subagent_file()
        sub.assistant("sub_before", at(5), output_tokens=100)
        sub.assistant("sub_in_first", at(0, 3), output_tokens=1000)
        sub.assistant("sub_in_second", at(10, 2), output_tokens=2000, input_tokens=7)
        sub.assistant("sub_after", at(20), output_tokens=5)
        self.ingest()
        first, second = self.records()
        self.assertEqual(first["subagent_models"]["claude-opus-5-5"]["output"], 1000)
        self.assertEqual(second["subagent_models"]["claude-opus-5-5"]["output"], 2000)
        self.assertEqual(second["subagent_models"]["claude-opus-5-5"]["input"], 7)
        self.assertEqual(second["subagent_api_calls"], 1)
        self.assertEqual(first["models"]["claude-opus-5-5"]["output"], 1)

    def test_subagent_cost_is_reported_and_included_in_usd_equiv(self):
        self.simple_turn("go", 0, "msg_1", output_tokens=1000)
        self.subagent_file().assistant("sub_1", at(0, 3), output_tokens=2000)
        self.ingest()
        (record,) = self.records()
        self.assertAlmostEqual(record["subagent_usd"], 2000 * 20.00 / 1e6)
        self.assertAlmostEqual(record["usd_equiv"], 3000 * 20.00 / 1e6)

    def test_subagent_streaming_duplicates_are_deduped_across_records(self):
        self.simple_turn("go", 0, "msg_1")
        sub = self.subagent_file()
        sub.assistant("sub_1", at(0, 2), output_tokens=10)
        sub.assistant("sub_1", at(0, 3), output_tokens=30)
        self.ingest()
        (record,) = self.records()
        self.assertEqual(record["subagent_models"]["claude-opus-5-5"]["output"], 30)
        self.assertEqual(record["subagent_api_calls"], 1)

    def test_without_a_subagents_directory_the_subagent_fields_are_empty(self):
        self.simple_turn("go", 0, "msg_1")
        self.ingest()
        (record,) = self.records()
        self.assertEqual((record["subagent_usd"], record["subagent_models"]), (0, {}))


class ClassificationTests(LedgerTestCase):
    def test_a_sweep_prompt_is_monitoring_with_high_confidence(self):
        self.simple_turn("RIV + GitHub sweep", 0, "msg_1")
        self.ingest()
        (record,) = self.records()
        self.assertEqual(
            (record["goal"], record["goal_rule"], record["goal_conf"]),
            ("monitoring", "P06_sweep_poll", "high"),
        )

    def test_tool_calls_become_a_signature_histogram_that_drives_the_goal(self):
        self.transcript.user("tidy up", at(0))
        self.transcript.assistant(
            "msg_1",
            at(0, 5),
            stop_reason="tool_use",
            output_tokens=900,
            tools=[
                ("t1", "Bash", {"command": "make test"}),
                ("t2", "Edit", {"file_path": "/x/app.py"}),
                ("t3", "Bash", {"command": "make check"}),
            ],
        )
        self.transcript.assistant("msg_2", at(0, 9), output_tokens=10)
        self.ingest()
        (record,) = self.records()
        self.assertEqual(record["tool_sig"], {"test": 2, "edit_code": 1})
        self.assertEqual(
            (record["goal"], record["goal_rule"]), ("implementation", "T1_tools")
        )

    def test_repeated_streaming_records_count_each_tool_call_once(self):
        self.transcript.user("go", at(0))
        for second in (1, 2):
            self.transcript.assistant(
                "msg_1", at(0, second), tools=[("t1", "Bash", {"command": "make test"})]
            )
        self.ingest()
        self.assertEqual(self.records()[0]["tool_sig"], {"test": 1})

    def test_compaction_summaries_are_overhead(self):
        self.transcript.user(
            "This session is being continued", at(0), isCompactSummary=True
        )
        self.transcript.assistant("msg_1", at(0, 5))
        self.ingest()
        (record,) = self.records()
        self.assertEqual(
            (record["goal"], record["prompt_kind"]), ("overhead", "compact_summary")
        )

    def test_prompt_kind_comes_from_the_records_origin(self):
        self.transcript.user("hello", at(0), origin="task-notification")
        self.transcript.assistant("msg_1", at(0, 5))
        self.ingest()
        self.assertEqual(self.records()[0]["prompt_kind"], "task-notification")

    def test_prompt_id_is_carried_over(self):
        self.transcript.user("hello", at(0), prompt_id="prompt-abc")
        self.transcript.assistant("msg_1", at(0, 5))
        self.ingest()
        self.assertEqual(self.records()[0]["prompt_id"], "prompt-abc")

    def test_assistant_records_with_no_user_prompt_form_a_promptless_turn(self):
        self.transcript.assistant("msg_1", at(0, 5), output_tokens=3)
        self.ingest()
        (record,) = self.records()
        self.assertEqual(
            (record["prompt_kind"], record["goal_rule"]), ("none", "P00_no_prompt")
        )


class IssueRefTests(unittest.TestCase):
    def test_finds_linear_keys_and_hash_numbers_once_each(self):
        prompt = "Work on RIV-123 and PLT-12 (see #45; also PR #45). Not UTF-8, not CVE-2024-1."
        self.assertEqual(turn_ledger.issue_refs(prompt), ["RIV-123", "PLT-12", "#45"])

    def test_ignores_html_entities_and_words_with_a_hash_inside(self):
        self.assertEqual(turn_ledger.issue_refs("&#123; abc#9"), [])

    def test_recorded_on_the_ledger_line(self):
        scratch = tempfile.TemporaryDirectory()
        self.addCleanup(scratch.cleanup)
        facts = turn_ledger.TurnFacts(
            agent="claude",
            session_id=SESSION,
            cwd="/tmp",
            prompt="please look at TOO-7",
            prompt_id=None,
            prompt_kind="human",
            flags="",
            ts_start=at(0),
            ts_end=at(1),
            models={},
            api_calls=0,
            cold_calls=0,
            ctx_max=0,
            tool_sig={},
            tokens_by_signature={},
        )
        self.assertEqual(turn_ledger.build_record(facts)["issue_refs"], ["TOO-7"])


class HookProcessTests(LedgerTestCase):
    def start(self, *args, stdin_text, home=None):
        env = {**os.environ, "TURN_LEDGER_HOME": str(home or self.home)}
        process = subprocess.Popen(
            [sys.executable, str(SCRIPT), "hook", *args],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
        )
        process.stdin.write(stdin_text)
        process.stdin.close()
        return process

    def run_hook(self, event, *args, home=None):
        process = self.start(*args, stdin_text=json.dumps(event), home=home)
        stdout, stderr = process.stdout.read(), process.stderr.read()
        return process.wait(), stdout, stderr

    def event(self, name="Stop", **overrides):
        event = {
            "hook_event_name": name,
            "session_id": SESSION,
            "transcript_path": str(self.transcript.path),
            "cwd": CREW_CWD,
        }
        return {**event, **overrides}

    def test_the_hook_reads_stdin_writes_the_ledger_and_prints_nothing(self):
        self.simple_turn("go", 0, "msg_1", output_tokens=5)
        code, stdout, stderr = self.run_hook(self.event())
        self.assertEqual((code, stdout, stderr), (0, "", ""))
        self.assertEqual(len(self.records()), 1)

    def test_a_missing_transcript_is_logged_with_context_and_exits_zero(self):
        event = self.event(transcript_path=str(self.root / "nope.jsonl"))
        code, stdout, _ = self.run_hook(event)
        self.assertEqual((code, stdout), (0, ""))
        log = (self.home / "errors.log").read_text()
        self.assertIn("event=Stop", log)
        self.assertIn(f"session_id={SESSION}", log)
        self.assertIn("Traceback", log)
        self.assertIn("FileNotFoundError", log)

    def test_a_session_start_before_the_transcript_exists_is_not_an_error(self):
        event = self.event(
            "SessionStart", transcript_path=str(self.root / "later.jsonl")
        )
        code, _, _ = self.run_hook(event)
        self.assertEqual(code, 0)
        self.assertFalse((self.home / "errors.log").exists())

    def test_garbage_on_stdin_is_logged_and_exits_zero(self):
        process = self.start(stdin_text="not json at all")
        process.wait()
        self.assertEqual(process.returncode, 0)
        log = (self.home / "errors.log").read_text()
        self.assertIn("event=?", log)
        self.assertIn("Traceback", log)

    def test_an_unsafe_session_id_is_logged_not_used_as_a_path(self):
        code, _, _ = self.run_hook(self.event(session_id="../../etc/evil"))
        self.assertEqual(code, 0)
        self.assertIn("unsafe session_id", (self.home / "errors.log").read_text())
        self.assertFalse((self.root / "etc").exists())

    def test_bad_arguments_still_exit_zero(self):
        process = self.start("--agent", "nonsense", stdin_text="{}")
        _, stderr = process.communicate()
        self.assertEqual(process.returncode, 0)
        self.assertIn("nonsense", (self.home / "errors.log").read_text())

    def test_an_unwritable_ledger_home_reports_on_stderr_and_exits_zero(self):
        blocker = self.root / "blocker"
        blocker.write_text("a file where the ledger directory should be")
        self.simple_turn("go", 0, "msg_1")
        code, _, stderr = self.run_hook(self.event(), home=blocker / "ledger")
        self.assertEqual(code, 0)
        self.assertIn("could not write errors.log", stderr)

    def test_overlapping_invocations_cannot_double_append(self):
        for index in range(3):
            self.simple_turn(f"turn {index}", index * 10, f"msg_{index}")
        stdin_text = json.dumps(self.event())
        processes = [self.start(stdin_text=stdin_text) for _ in range(8)]
        for process in processes:
            process.wait()
        self.assertEqual([p.returncode for p in processes], [0] * 8)
        self.assertEqual(
            [r["prompt_head"] for r in self.records()], ["turn 0", "turn 1", "turn 2"]
        )
        self.assertFalse((self.home / "errors.log").exists())


class IdentityTests(unittest.TestCase):
    def identify(self, relative):
        return turn_ledger.identify(str(Path.home() / "gt" / relative))

    def test_roles_come_from_the_working_directory(self):
        cases = {
            "dotfiles/crew/marsha": ("crew", "dotfiles", "marsha"),
            "monorepo/polecats/atom/monorepo": ("polecat", "monorepo", "atom"),
            "mayor": ("mayor", "town", "mayor"),
            "mayor/rig": ("mayor", "town", "mayor"),
            "deacon": ("deacon", "town", "deacon"),
            "deacon/dogs/alpha": ("dog", "town", "alpha"),
            "deacon/dogs/boot": ("boot", "town", "boot"),
            "monorepo/witness": ("witness", "monorepo", "witness"),
            "monorepo/refinery/rig": ("refinery", "monorepo", "refinery"),
            "dotfiles/crew/marsha/.claude/worktrees/x": ("crew", "dotfiles", "marsha"),
        }
        for relative, expected in cases.items():
            with self.subTest(relative=relative):
                self.assertEqual(self.identify(relative), expected)

    def test_anything_else_is_role_other(self):
        self.assertEqual(turn_ledger.identify("/tmp/scratch"), ("other", None, None))
        self.assertEqual(
            turn_ledger.identify(str(Path.home() / "Development/x")),
            ("other", None, None),
        )
        self.assertEqual(turn_ledger.identify(""), ("other", None, None))


if __name__ == "__main__":
    unittest.main()
