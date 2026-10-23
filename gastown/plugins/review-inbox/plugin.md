+++
name = "review-inbox"
description = "Turn River's direct GitHub review requests into issues on Linear team RIV"
version = 1

[gate]
type = "cooldown"
duration = "15m"

[tracking]
labels = ["plugin:review-inbox", "category:relay"]
digest = true

[execution]
timeout = "5m"
notify_on_failure = false
severity = "medium"
+++

# Review Inbox

When someone asks River directly for a GitHub review, this plugin opens one
issue for it on Linear team RIV and keeps that issue in step with the PR.

`review_inbox.py` reads GitHub itself and makes every decision: which PRs are
new, what changed, what to write, who to mail, and when to escalate. You (the
dog) do the one thing only an LLM session can do: make the Linear calls it
prints, exactly as printed, and save what they return. Do not decide anything
yourself.

**Dry run.** Until `~/gt/.runtime/review-inbox/DELIVER` exists, the script logs
the Linear calls and mails it would make to
`~/gt/.runtime/review-inbox/dry-run.log` and prints `DONE`, so you make no
Linear calls at all. Do not create or remove that file.

## Rules

- Call Linear ONLY through the `prod-full-suite` MCP server's `Arcade_UseTool`,
  and ONLY the calls `review_inbox.py` prints. Never read or write Linear
  otherwise.
- Never write to GitHub. Never sling, and never run `gt mail send` or
  `gt escalate` yourself. The script does all mail and escalation.
- If a tool answers with an authorization link or asks you to sign in, do NOT
  follow it. Treat it as a failed call (Step 2).
- If the script prints `NOTHING_CHANGED` or `DONE`, stop after Step 1.

## Step 1: Ask review_inbox.py what to do

```bash
python3 ~/gt/plugins/review-inbox/review_inbox.py check
```

- `NOTHING_CHANGED`: go to Record Result with `result:success`. You are done.
- `DONE <summary>`: go to Record Result with `result:success` and the summary.
  You are done.
- `CALLS <n>` followed by `n` lines `CALL <id> <json>`: go to Step 2.
- Exit code not 0: the script already counted the failure. Go to Record Result
  with `result:failure` and its error output.

## Step 2: Make each call, in order

For EACH `CALL` line, top to bottom: the JSON holds `tool_name` and `inputs`.
Call `Arcade_UseTool` on `prod-full-suite` with that `tool_name` and those
`inputs`, copied exactly. For example, the line

```text
CALL c1 {"tool_name": "Linear.AddComment", "inputs": {"issue": "RIV-12"}}
```

means `Arcade_UseTool` with `tool_name` `Linear.AddComment` and `inputs`
`{"issue": "RIV-12"}`. Real lines carry more inputs; pass them all.

Write the tool's JSON result, complete and unedited, to
`~/gt/.runtime/review-inbox/pending/<id>.json`:

```bash
cat > ~/gt/.runtime/review-inbox/pending/c1.json <<'REVIEW_INBOX_RESULT'
{"id": "...", "issue_identifier": "RIV-12", "...": "the whole result"}
REVIEW_INBOX_RESULT
```

If a call fails, write nothing for it, make NO further calls, and remember its
error.

## Step 3: Apply

```bash
python3 ~/gt/plugins/review-inbox/review_inbox.py apply
```

If a call failed in Step 2, pass its error:

```bash
python3 ~/gt/plugins/review-inbox/review_inbox.py apply \
  "c2 Linear.UpdateIssue: <its error>"
```

It prints one summary line, e.g. `review-inbox: 2 PR(s) written to RIV, 1
mail(s) sent`. Exit code 0: Record Result with `result:success` and that line.
Otherwise the script already counted the failure and will retry the unwritten
calls next run: Record Result with `result:failure` and its error output.

## Record Result

```bash
bd create "review-inbox: <summary line>" -t chore --ephemeral \
  -l type:plugin-run,plugin:review-inbox,result:<success|failure> \
  -d "<summary line or error>" --silent 2>/dev/null || true
```

Do not escalate on failure; `review_inbox.py` owns escalation.

## What it does (reference)

- **Source:** `gh search prs --state=open "user-review-requested:@me"`, so only
  requests to River herself, not to a team she is on.
- **New request:** one RIV issue per PR, keyed by repo and PR number in
  `~/gt/.runtime/review-inbox/state.json`. Title `Review: #NNNN <PR title>`,
  state Todo, label `needs-river`, assigned to River. The description has the
  author, size, risk label, why River was asked (CODEOWNERS or added manually),
  the PR link, and the first two lines of the PR description.
- **Large or risky PRs:** over 500 changed lines, or labelled `risk:high`. The
  script mails `monorepo/crew/gigi` asking for a read-only preliminary review,
  with the PR and RIV links.
- **Request withdrawn, PR merged or closed, or River reviewed:** a comment, then
  Done.
- **New commits after River's review, or River asked again:** a comment, then
  `needs-river` again.
- **Signed:** every description and comment ends `~ Δ Delta, downstream of
  River`, so riv-relay skips them.
- **Failures:** a call that fails is retried next run, skipping calls that
  already succeeded. The 5th failed run in a row makes one `gt escalate`,
  fingerprint `review-inbox`.
