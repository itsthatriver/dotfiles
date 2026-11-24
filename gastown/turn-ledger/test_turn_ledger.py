"""Fixture tests for the turn ledger. Run: python3 -m unittest discover gastown/turn-ledger"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import goals  # noqa: E402


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


if __name__ == "__main__":
    unittest.main()
