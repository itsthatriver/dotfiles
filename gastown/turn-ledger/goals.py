"""Rules-based goal labels for agent turns.

Ported from the phagey token analysis of 2026-11-24
(~/.local/share/phagey/analysis-2026-11-24/tokens/): classify.py supplies the
prompt rules and the tool-profile vote, sigs.py supplies the tool signatures.
Rule ids (P06_sweep_poll, T1_tools, ...) are kept so a ledger record's
goal_rule matches the analysis.

Layer 1: decisive prompt patterns, first match wins.
Layer 2: token-weighted vote over tool-call signatures. "Support" signatures
         (reading, exploring) only count when nothing purposeful is present.
Layer 3: the fallback goal attached to the matched prompt rule, else "other".
"""

from __future__ import annotations

import re
from collections import Counter

# Tool signatures, most specific first. Bash commands are matched against the
# command head, so the first rule that hits wins.
BASH_RULES = [
    ("prime", r"\bgt (prime|hook)\b"),
    (
        "maint",
        r"\bdolt\b|plugins/|\bgt (costs|doctor|plugin|stale|compact|reaper|rebuild)"
        r"|rebuild-gt|\bbd (doctor|compact|sync|admin)|gt\.old|launchctl",
    ),
    (
        "ci_poll",
        r"watch-wake|watch-approvals|next-sweep|pr-watch|refinery-guard"
        r"|\.runtime/(riv-relay|review-inbox)|gh-phagey",
    ),
    ("mail", r"\bgt (mail|nudge|peek)\b"),
    (
        "mgmt_cmd",
        r"sling-safe|gigi-tools|\bgt (sling|convoy|polecat|crew|rig|deacon|witness|refinery"
        r"|dog|boot|escalate|handoff|mol|molecule|formula|swarm|mq|done|session|status"
        r"|agents|feed|unsling|hooks?)\b|\btmux\b",
    ),
    (
        "bead",
        r"\bbd (create|update|close|show|list|ready|dep|comment|children|search|label)\b",
    ),
    (
        "upkeep",
        r"\bgit (merge|rebase|cherry-pick|pull|reset)\b|gh pr (update-branch|merge|ready)"
        r"|push .*(--force|-f\b)|merge-conflict|\bconflict",
    ),
    (
        "gh_comment",
        r"gh pr (comment|review)|gh issue comment|(-X|--method) POST[^|;]*(comments|replies|reviews)"
        r"|addPullRequestReview|resolveReviewThread",
    ),
    (
        "ci_poll",
        r"gh pr (checks|view|list|status|diff)|gh run |gh api|gh search|gh issue (list|view)"
        r"|gh-phagey|gh auth|review_inbox|slack_triage",
    ),
    (
        "test",
        r"\bmake (check|test|lint|build|fmt|sql|gen)|\bgo (test|vet|build)\b|golangci|pytest"
        r"|\bruff\b|\bbiome\b|\bbun\b|\bnpm\b|\bpnpm\b|\btsc\b|\buv (run|sync)\b|prettier|\bmise\b",
    ),
    (
        "git_write",
        r"\bgit (add|commit|push|checkout|switch|worktree|stash|branch|tag|apply|restore|mv|rm)\b",
    ),
    (
        "explore",
        r"^(cd [^;&|]+(&&|;)\s*)?(ls|cat|head|tail|grep|rg|find|sed|awk|wc"
        r"|git (log|diff|show|status|blame|rev-parse|remote|fetch)|tree|stat|jq|file|which|pwd"
        r"|echo|date|python3?|sleep|test|diff|for|ps|lsof|curl)\b",
    ),
    ("explore", r"^[A-Za-z_]\w*="),
]
_BASH_RULES = [(name, re.compile(pattern)) for name, pattern in BASH_RULES]

ARCADE_COMMENT = re.compile(
    r"^(Linear\.(AddComment|ReplyToComment|UpdateComment|AddProjectComment|ReplyToProjectComment)"
    r"|Slack\.(SendMessage|PostMessage|Reply\w*|CreateConversation|SendDm\w*)"
    r"|Github\.\w*(Comment|Review|Reply)\w*)$"
)
ARCADE_READ = re.compile(
    r"^(Linear\.(Get|List|Search)\w*|Slack\.(Search|Get|List|WhoAmI)\w*|Github\.(Get|List|Search)\w*"
    r"|Datadog\.\w+|Lightdash\.\w+|Google\w*\.(Get|List|Search)\w*)$"
)
ARCADE_MGMT = re.compile(
    r"^(Linear\.(Create|Update|Upsert|Transition|Delete)\w*|Github\.(Create|Update|Merge|Close)\w*)$"
)

DELEGATE_TOOLS = {
    "Agent",
    "SendMessage",
    "spawn_agent",
    "send_message",
    "followup_task",
    "ListAgents",
}
WAIT_TOOLS = {
    "CronCreate",
    "CronDelete",
    "CronList",
    "ScheduleWakeup",
    "Monitor",
    "TaskStop",
    "TaskOutput",
    "RemoteTrigger",
    "sleep",
    "wait",
}


def signature(label: str, argument: str) -> str:
    """Map one tool call (label and argument head) to a coarse activity label."""
    if label in ("Bash", "exec"):
        for name, pattern in _BASH_RULES:
            if pattern.search(argument):
                return name
        return "bash_other"
    if label.startswith("Arcade:"):
        tool = label[len("Arcade:") :]
        if ARCADE_COMMENT.match(tool):
            return "comment"
        if ARCADE_MGMT.match(tool):
            return "issue_mgmt"
        if ARCADE_READ.match(tool):
            return "poll_read"
        return "arcade_other"
    if label in ("Edit", "Write", "NotebookEdit"):
        return "edit_doc" if argument.endswith((".md", ".txt", ".mdx")) else "edit_code"
    if label in ("Read", "Grep", "Glob", "WebFetch", "WebSearch") or label.startswith(
        "mcp__claude_ai_"
    ):
        return "read"
    if label in DELEGATE_TOOLS:
        return "delegate"
    if label in WAIT_TOOLS:
        return "wait"
    return "neutral"


# Each rule: (id, goal, fallback goal, pattern). A goal of None defers to the
# tool profile, then to the fallback. A goal of "PLUGIN" maps the matched
# plugin name through PLUGIN_GOAL.
PROMPT_RULES = [
    (
        "P01_compaction",
        "overhead",
        None,
        r"^(This session is being continued|<summary>)",
    ),
    ("P02_interrupt", "overhead", None, r"^\[Request interrupted"),
    (
        "P03_slash_local",
        "overhead",
        None,
        r"^(<command-name>|<local-command|Caveat: The messages below)",
    ),
    ("P04_boot_triage", "monitoring", None, r"^\[GAS TOWN\] boot <- daemon"),
    (
        "P05_patrol",
        "monitoring",
        None,
        r"^\[GAS TOWN\] \S+.*\bpatrol\b|\bpatrol\b.*\bgt prime",
    ),
    ("P06_sweep_poll", "monitoring", None, r"\bsweep\b|\bpoll(s|ing)?\b"),
    (
        "P07_plugin_mail",
        "management",
        None,
        r"^📬 You have new mail from daemon\. Subject: Plugin: ",
    ),
    ("P08_dog_plugin", "PLUGIN", None, r"Plugin ([\w-]+) dispatched"),
    ("P09_polecat_done", "management", None, r"^POLECAT_DONE"),
    ("P10_merge_ready", "pr_upkeep", None, r"^MERGE_READY"),
    (
        "P11_review",
        "review",
        None,
        r"code[- ]review|\breview (request|this|the|pr|my|these)\b|^/?review\b|please review"
        r"|Review request|<action>review</action>",
    ),
    (
        "P12_pr_upkeep",
        "pr_upkeep",
        None,
        r"merge main|\brebase\b|merge[- ]conflict|refresh[- ]pr|update.branch|\bconflicts?\b",
    ),
    (
        "P13_message",
        None,
        "management",
        r"^(📬|🚨|<system-reminder> QUEUED NUDGE|\[from )",
    ),
    (
        "P14_work_assign",
        None,
        "implementation",
        r"^Work slung|\[GAS TOWN\] polecat .*assigned|^# AGENTS\.md instructions",
    ),
    (
        "P15_resume",
        None,
        "overhead",
        r"^E-stop cleared|^(keep going|continue|go on|resume)\b",
    ),
    ("P16_gt_startup", None, "overhead", r"^\[GAS TOWN\]"),
    ("P17_bg_task_done", None, "monitoring", r"^<task-notification>"),
    (
        "P18_ask_research",
        "research",
        None,
        r"^(explain|why|what|how|where|who|can you (explain|look|check|find)|look (at|into)|investigate"
        r"|find out|summari[sz]e|walk me through)",
    ),
]
_PROMPT_RULES = [
    (
        rule_id,
        goal,
        fallback,
        re.compile(pattern, re.S if rule_id == "P01_compaction" else re.S | re.I),
    )
    for rule_id, goal, fallback, pattern in PROMPT_RULES
]
PROMPT_WINDOW = 400

PLUGIN_GOAL = {
    "riv-relay": "monitoring",
    "review-inbox": "monitoring",
    "slack-triage": "monitoring",
    "github-sheriff": "monitoring",
    "quality-review": "review",
    "dolt-backup": "maintenance",
    "dolt-archive": "maintenance",
    "compactor-dog": "maintenance",
    "dolt-log-rotate": "maintenance",
    "rebuild-gt": "maintenance",
    "submodule-commit": "maintenance",
    "gitignore-reconcile": "maintenance",
    "git-hygiene": "maintenance",
    "tool-updater": "maintenance",
    "stuck-agent-dog": "monitoring",
}

# Signature -> goal. "Support" signatures only count when nothing purposeful is present.
SIGNATURE_GOAL = {
    "edit_code": "implementation",
    "test": "implementation",
    "git_write": "implementation",
    "upkeep": "pr_upkeep",
    "gh_comment": "commenting",
    "comment": "commenting",
    "ci_poll": "monitoring",
    "poll_read": "monitoring",
    "wait": "monitoring",
    "mail": "management",
    "mgmt_cmd": "management",
    "bead": "management",
    "delegate": "management",
    "issue_mgmt": "management",
    "maint": "maintenance",
    "edit_doc": "research",
    "prime": "overhead",
}
SUPPORT_GOAL = {
    "explore": "research",
    "read": "research",
    "bash_other": "other",
    "arcade_other": "other",
}
GOAL_WEIGHT = {"implementation": 1.5}
CONFIDENT_SHARE = 0.6


def classify_by_tools(
    tokens_by_signature: dict[str, float],
) -> tuple[str | None, float]:
    """Return the winning goal and its share of the vote (0 when nothing votes)."""
    purposeful: Counter[str] = Counter()
    for sig, tokens in tokens_by_signature.items():
        goal = SIGNATURE_GOAL.get(sig)
        if goal and goal != "overhead":
            purposeful[goal] += tokens * GOAL_WEIGHT.get(goal, 1.0)
    if purposeful:
        goal, votes = purposeful.most_common(1)[0]
        return goal, votes / sum(purposeful.values())
    support: Counter[str] = Counter()
    for sig, tokens in tokens_by_signature.items():
        goal = SUPPORT_GOAL.get(sig) or (
            SIGNATURE_GOAL["prime"] if sig == "prime" else None
        )
        if goal:
            support[goal] += tokens
    if support:
        goal, votes = support.most_common(1)[0]
        return goal, votes / sum(
            support.values()
        ) * 0.5  # support-only votes never reach high confidence
    return None, 0.0


def _confidence(share: float) -> str:
    return "high" if share >= CONFIDENT_SHARE else "low"


def classify(
    prompt: str, tokens_by_signature: dict[str, float], flags: str = ""
) -> tuple[str, str, str, str]:
    """Return (goal, goal_rule, goal_conf, subtype) for one turn."""
    prompt = (prompt or "").strip()
    if "isCompactSummary" in flags:
        return "overhead", "P01_compaction", "high", ""
    if not prompt:
        goal, _ = classify_by_tools(tokens_by_signature)
        return goal or "overhead", "P00_no_prompt", "low", ""
    for rule_id, goal, fallback, pattern in _PROMPT_RULES:
        match = pattern.search(prompt[:PROMPT_WINDOW])
        if not match:
            continue
        if goal == "PLUGIN":
            plugin = match.group(1)
            return (
                PLUGIN_GOAL.get(plugin, "other"),
                rule_id,
                "high" if plugin in PLUGIN_GOAL else "low",
                plugin,
            )
        subtype = ""
        if rule_id == "P07_plugin_mail":
            subtype = re.search(r"Plugin: ([\w-]+)", prompt).group(1)
        if goal:
            return goal, rule_id, "high", subtype
        tool_goal, share = classify_by_tools(tokens_by_signature)
        if tool_goal:
            return tool_goal, rule_id + "+tools", _confidence(share), subtype
        return fallback, rule_id + "+fallback", "low", subtype
    tool_goal, share = classify_by_tools(tokens_by_signature)
    if tool_goal:
        return tool_goal, "T1_tools", _confidence(share), ""
    return "other", "T2_nothing", "low", ""
