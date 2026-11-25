"""Fixture tests for check-delegates.sh. Run: python3 -m unittest discover gastown/plugins/phagey-sweep"""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent / "check-delegates.sh"
DELEGATE_RIGS = {
    "monorepo": "crew/gigi",
    "gs": "crew/drummer",
    "ml": "crew/lovelace",
    "dotfiles": "crew/marsha",
    "data": "crew/hopper",
}

# Output is padded with thousands of lines so that a `gt ... | grep -q` pipeline
# under pipefail would SIGPIPE gt and fail, the way the real, chatty gt does.
FAKE_GT = textwrap.dedent(
    """\
    #!/usr/bin/env bash
    home=$FAKE_GT_HOME
    case "$1" in
      agents)
        [[ -e $home/AGENTS_FAIL ]] && { echo "daemon unreachable"; exit 1; }
        cat "$home/agents" ;;
      rig)
        echo "$3"
        if grep -Fxq "$3" "$home/parked"; then echo "  Status: PARKED (local)"; else echo "  Status: OPERATIONAL"; fi
        seq 1 20000 ;;
      peek)
        if grep -Fxq "$2" "$home/peek_failing"; then echo "can't find session for $2" >&2; exit 1; fi
        seq 1 20000
        if grep -Fxq "$2" "$home/prompting"; then printf '  ❯ 1. Yes\\n  2. No\\n'; fi ;;
    esac
    """
)


class CheckDelegatesTest(unittest.TestCase):
    def setUp(self) -> None:
        self.home = Path(tempfile.mkdtemp())
        bin_dir = self.home / "bin"
        bin_dir.mkdir()
        fake_gt = bin_dir / "gt"
        fake_gt.write_text(FAKE_GT)
        fake_gt.chmod(0o755)
        (self.home / "gt").mkdir()
        self.state = self.home / "delegates-live"
        self.env = {
            **os.environ,
            "HOME": str(self.home),
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FAKE_GT_HOME": str(self.home),
            "CHECK_DELEGATES_STATE": str(self.state),
        }
        self.set_parked()
        self.set_prompting()
        self.set_peek_failing()

    def set_live(self, *rigs: str) -> None:
        lines = []
        for rig in rigs:
            lines += [f"── {rig} ──", f"  👷 {DELEGATE_RIGS[rig]}"]
        self.write_agents(lines)

    def write_agents(self, lines: list[str]) -> None:
        (self.home / "agents").write_text("\n".join(lines) + "\n")

    def set_parked(self, *rigs: str) -> None:
        (self.home / "parked").write_text("".join(f"{rig}\n" for rig in rigs))

    def set_prompting(self, *agents: str) -> None:
        (self.home / "prompting").write_text("".join(f"{agent}\n" for agent in agents))

    def set_peek_failing(self, *agents: str) -> None:
        (self.home / "peek_failing").write_text("".join(f"{agent}\n" for agent in agents))

    def check(self) -> subprocess.CompletedProcess:
        return subprocess.run(
            [str(SCRIPT)], env=self.env, capture_output=True, text=True, timeout=60
        )

    def test_everyone_live_is_clean(self) -> None:
        self.set_live(*DELEGATE_RIGS)
        result = self.check()
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_agent_down_on_operational_rig_is_reported_every_time(self) -> None:
        self.set_live("monorepo", "gs", "ml", "dotfiles")
        for _ in range(2):
            result = self.check()
            self.assertEqual((result.returncode, result.stdout), (1, "DOWN data/crew/hopper\n"))

    def test_agent_that_stays_down_on_parked_rig_is_quiet(self) -> None:
        self.set_parked("ml")
        self.set_live("monorepo", "gs", "dotfiles", "data")
        result = self.check()
        self.assertEqual((result.returncode, result.stdout), (0, ""))

    def test_agent_that_drops_on_parked_rig_is_reported_once(self) -> None:
        self.set_parked("dotfiles")
        self.set_live(*DELEGATE_RIGS)
        self.assertEqual(self.check().stdout, "")
        self.set_live("monorepo", "gs", "ml", "data")
        dropped = self.check()
        self.assertEqual((dropped.returncode, dropped.stdout), (1, "DOWN dotfiles/crew/marsha\n"))
        still_down = self.check()
        self.assertEqual((still_down.returncode, still_down.stdout), (0, ""))

    def test_prompt_is_flagged_on_any_rig(self) -> None:
        self.set_parked("gs")
        self.set_live(*DELEGATE_RIGS)
        self.set_prompting("gs/crew/drummer", "monorepo/crew/gigi")
        result = self.check()
        self.assertEqual(
            (result.returncode, result.stdout),
            (1, "PROMPT monorepo/crew/gigi\nPROMPT gs/crew/drummer\n"),
        )

    def test_agent_whose_name_is_a_prefix_of_a_live_one_is_down(self) -> None:
        self.write_agents(["── monorepo ──", "  👷 crew/gigi2", "── gs ──", "  👷 crew/drummer",
                           "── ml ──", "  👷 crew/lovelace", "── dotfiles ──", "  👷 crew/marsha",
                           "── data ──", "  👷 crew/hopper"])
        result = self.check()
        self.assertEqual((result.returncode, result.stdout), (1, "DOWN monorepo/crew/gigi\n"))

    def test_peek_failure_is_an_error_not_healthy(self) -> None:
        self.set_live(*DELEGATE_RIGS)
        self.set_peek_failing("gs/crew/drummer")
        result = self.check()
        self.assertEqual(result.returncode, 2)
        self.assertIn("gt peek gs/crew/drummer failed: can't find session", result.stderr)
        # A failed check leaves the state alone (see the parked-drop test below).
        self.assertFalse(self.state.exists())

    def test_parked_drop_is_still_reported_after_a_failed_check(self) -> None:
        # sweep.py reports only the check failure on exit 2 and drops the DOWN line, so
        # a failed run must not consume the one-time drop notice by rewriting the state.
        self.set_parked("dotfiles")
        self.set_live(*DELEGATE_RIGS)
        self.assertEqual(self.check().stdout, "")
        self.set_live("monorepo", "gs", "ml", "data")
        self.set_peek_failing("gs/crew/drummer")
        self.assertEqual(self.check().returncode, 2)
        self.set_peek_failing()
        retried = self.check()
        self.assertEqual((retried.returncode, retried.stdout), (1, "DOWN dotfiles/crew/marsha\n"))

    def test_nobody_live_records_empty_state(self) -> None:
        self.set_live()
        result = self.check()
        self.assertEqual(result.returncode, 1)
        self.assertEqual(self.state.read_text().strip(), "")

    def test_gt_agents_failure_is_an_error_and_keeps_state(self) -> None:
        self.state.write_text("dotfiles/crew/marsha\n")
        (self.home / "AGENTS_FAIL").touch()
        result = self.check()
        self.assertEqual((result.returncode, result.stdout), (2, ""))
        self.assertIn("gt agents failed: daemon unreachable", result.stderr)
        self.assertEqual(self.state.read_text(), "dotfiles/crew/marsha\n")


if __name__ == "__main__":
    unittest.main()
