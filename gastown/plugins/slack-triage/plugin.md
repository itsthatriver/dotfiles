+++
name = "slack-triage"
description = "Turn what needs River in Slack into issues on Linear team RIV"
version = 1

[gate]
type = "cooldown"
duration = "30m"

[tracking]
labels = ["plugin:slack-triage", "category:relay"]
digest = true

[execution]
timeout = "15m"
notify_on_failure = false
severity = "medium"
+++

# Slack Triage

River works from her RIV board, not from Slack. This plugin finds what in
Slack needs her to act and puts each item on RIV as an issue she can triage in
seconds and resolve with a one-line comment. **Task-shaped work only.** Live
chat stays in Slack; you are not a slow proxy for conversation.

You (the dog) do the two things only an LLM session can do: read Slack through
the Arcade gateway, and judge what needs River. `slack_triage.py` does
everything else: the time window, which threads already have an issue, the
exact Linear calls, and escalation. Do not write to Linear any other way.

**Dry run.** Until `~/gt/.runtime/slack-triage/DELIVER` exists, the script logs
the Linear calls it would make to `~/gt/.runtime/slack-triage/dry-run.log` and
prints `DONE`, so you make no Linear calls at all. Do not create or remove that
file.

## Rules

- Use ONLY the `prod-full-suite` MCP server's `Arcade_UseTool` (find tools with
  its `Arcade_SelectTools`). Read Slack with `Slack.SearchMessages`,
  `Slack.ListConversations`, `Slack.ListMessages`, `Slack.GetThread` and
  `Slack.GetMessage`. Make ONLY the Linear calls `slack_triage.py` prints.
- **Never post, react, forward or join anything in Slack.** Never DM anyone.
- If a tool answers with an authorization link or asks you to sign in, do NOT
  follow it. Treat it as a failed read (Step 5).
- Never run `gt mail send` or `gt escalate` yourself.
- Never put words in River's mouth. Every claim in an issue comes from a
  message you read in full.

## Step 1: Take the window

```bash
python3 ~/gt/plugins/slack-triage/slack_triage.py begin
```

- `BUSY`: another run is in progress. Record Result with `result:success` and
  `busy`. You are done.
- `WINDOW <start> <end>`: read Slack for messages posted at or after `<start>`
  and before `<end>` (UTC). Go to Step 2.

## Step 2: Read Slack for the window

River is `U0A1CB9AT3Q` (`@river`). Skip her own messages. Four sources:

1. **Mentions:** `Slack.SearchMessages` with query
   `@river -from:@river after:<start date minus 1 day>`, `sort` `timestamp`,
   `order` `desc`. Classic `after:` is a whole date and exclusive, so keep only
   results whose `posted_at` falls inside the window. Follow `next_cursor`
   until results are older than `<start>`.
2. **DMs and group DMs:** `Slack.ListConversations` with `conversation_types`
   `["im", "mpim"]`, `projection` `ids`, `include_archived` false. For each,
   `Slack.ListMessages` with `after` `<start>` and `before` `<end>`. A bot
   message counts only if it assigns River something (calendar reminders and
   other agents' FYIs do not).
3. **Threads she's in:** `Slack.SearchMessages` with query
   `from:@river after:<start date minus 3 days>`, `sort` `timestamp`. For each
   distinct thread, `Slack.GetThread` with `after` `<start>` to see new replies
   from other people.
4. **Her areas (discovery):** `Slack.SearchMessages` in channels she's in for
   new threads about platform, infra, security, auth, agents/MCP, tool
   recommendation, deployments/on-prem, coding-agent tooling, observability,
   ADRs/eng process, and feature flags/org model. Keep this light: one or two
   queries, top results only.

## Step 3: Decide what needs River

For each candidate, **read the whole thread** (`Slack.GetThread`) and any
truncated message in full (`Slack.GetMessage`). Drop it if River already
answered, reacted to close it out, or someone else resolved it.

What to file (calibrated by River):

- **`ask`, always:** a direct ask of River in a DM or @-mention (a question,
  a review, a decision, "can you include me"). It gets its own "Reply to
  <name>: …" issue even if another agent's issue covers the underlying work.
- **`answer`:** a reply River or an agent was waiting on, for a known RIV
  issue (it's in that issue's Refs, or the thread names it). Relay it
  verbatim into that issue. Never file a new issue for it.
- **`fyi` / `optional`, high bar:** a new public commitment made for River
  ("River will write this up"), or a technical finding in her areas that
  changes her work (a repro, a regression, a design decision). NOT incidents
  she isn't in (unless a major prod outage), votes, announcements, social
  chat, or progress updates.

When unsure, leave it out. River would rather miss an FYI than triage noise.

## Step 4: File through slack_triage.py

Write the items as a JSON array, one item per Slack thread, and pipe it in.
An empty array is fine: it records that the window was read.

```bash
python3 ~/gt/plugins/slack-triage/slack_triage.py plan <<'SLACK_TRIAGE_ITEMS'
[
  {"kind": "ask",
   "source": "<permalink of the message that asks River>",
   "title": "Reply to Guru: include Sterling in the on-prem discussions",
   "why": "One or two sentences: who asked what, where, and why it matters.",
   "ask": "The one thing River needs to do.",
   "default": "What happens or stays blocked if she doesn't.",
   "refs": ["RIV-45", "https://github.com/ArcadeAI/monorepo/pull/6299"],
   "suggested_reply": "A reply she could approve with one word. Optional."},
  {"kind": "answer",
   "source": "<permalink of the answer>",
   "issue": "RIV-12",
   "quote": "The answer, verbatim.",
   "summary": "One sentence on what it means for the issue."}
]
SLACK_TRIAGE_ITEMS
```

`fyi` and `optional` items take the same fields as `ask`; the script adds the
`FYI:` / `Optional:` title prefix. Titles start with a verb. Write Slack
mentions in a suggested reply as `<@USERID>`.

- `DONE <summary>`: Record Result with `result:success` and the summary.
- `CALLS <n>` followed by `n` lines `CALL <id> <json>`: go to Step 4b.
- Exit code not 0: the script already counted the failure. Record Result with
  `result:failure` and its error output. If the error names a bad item, the
  next run re-reads the same window, so fix it then.

## Step 4b: Make each call, in order

For EACH `CALL` line, top to bottom: call `Arcade_UseTool` on
`prod-full-suite` with that line's `tool_name` and `inputs`, copied exactly.
Write the tool's JSON result, complete and unedited, to
`~/gt/.runtime/slack-triage/pending/<id>.json`:

```bash
cat > ~/gt/.runtime/slack-triage/pending/c1.json <<'SLACK_TRIAGE_RESULT'
{"issue": {"identifier": "RIV-50", "...": "the whole result"}, "created": true}
SLACK_TRIAGE_RESULT
```

If a call fails, write nothing for it, make NO further calls, and remember its
error. Then apply:

```bash
python3 ~/gt/plugins/slack-triage/slack_triage.py apply
# or, after a failed call:
python3 ~/gt/plugins/slack-triage/slack_triage.py apply "c2 Linear.CreateIssue: <its error>"
```

Exit code 0: Record Result with `result:success` and the line it prints.
Otherwise Record Result with `result:failure`; the next run re-reads the window
and skips what was already written.

## Step 5: A Slack read failed

```bash
python3 ~/gt/plugins/slack-triage/slack_triage.py fail "<tool>: <its error>"
```

Then Record Result with `result:failure`.

## Record Result

```bash
bd create "slack-triage: <summary line>" -t chore --ephemeral \
  -l type:plugin-run,plugin:slack-triage,result:<success|failure> \
  -d "<summary line or error>" --silent 2>/dev/null || true
```

Do not escalate on failure; `slack_triage.py` escalates on the 5th failure in a
row.

## What happens next (reference)

- Issues are Todo, assigned to River, labelled `needs-river`,
  `agent:phagey` and `slack`, and signed `~ Δ Delta, downstream of River` so riv-relay
  skips them.
- River answers on the issue: `@phagey send`, `@phagey send: <text>`,
  `@phagey done` / `drop`, or a free-form ask. riv-relay routes her reply to
  phagey, who acts on it. phagey posts to Slack only the exact text she
  approved.
- A new message in a thread that already has an issue becomes a comment there,
  and the issue goes back to Todo with `needs-river`.
