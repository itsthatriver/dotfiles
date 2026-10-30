+++
name = "riv-relay"
description = "Relay River's comments and checkbox ticks on Linear team RIV to Gas Town agents via gt mail"
version = 1

[gate]
type = "cooldown"
duration = "5m"

[tracking]
labels = ["plugin:riv-relay", "category:relay"]
digest = true

[execution]
timeout = "4m"
notify_on_failure = false
severity = "medium"
+++

# RIV Relay

River answers agents on Linear team RIV. This plugin carries her answers to the
right agent's Gas Town mailbox, so she never has to say "I posted".

You (the dog) do the two things only an LLM session can do: read Linear through
the Arcade gateway and hand the result to `relay.py`. The script decides
everything else: what changed, what to relay, who gets it, what state to keep,
and when to escalate. Do not make those decisions yourself.

**Dry run.** Until `~/gt/.runtime/riv-relay/DELIVER` exists, `relay.py` writes
the mails it would send to `~/gt/.runtime/riv-relay/dry-run.log` and sends
nothing. Do not create or remove that file.

## Rules

- Read Linear ONLY through the `prod-full-suite` MCP server's `Arcade_UseTool`,
  and call ONLY `Linear.ListIssues` and `Linear.GetIssue`. Never write to Linear.
- If a tool answers with an authorization link or asks you to sign in, do NOT
  follow it. Treat it as a failed read (Step 5).
- Never run `gt mail send` or `gt escalate` yourself. `relay.py` does both.
- If nothing changed, stop after Step 2. No other reads, no summaries.

## Step 1: List RIV issues

Call `Arcade_UseTool` on `prod-full-suite` with:

```json
{"tool_name": "Linear.ListIssues", "inputs": {"team": "RIV", "limit": 50}}
```

If the result has `pagination.has_next_page: true`, call it again with
`"end_cursor"` set to `pagination.end_cursor` until it is false.

If any call fails, go to Step 5.

## Step 2: Ask relay.py what changed

Pass one line per issue: its `identifier`, a space, and its `updated_at`,
copied exactly. Every issue from Step 1, nothing else.

```bash
python3 ~/gt/plugins/riv-relay/relay.py check <<'LISTING'
RIV-7 2026-10-21T22:04:11.253Z
RIV-3 2026-10-21T23:37:51.294Z
LISTING
```

- `NOTHING_CHANGED`: go to Record Result with `result:success`. You are done.
- `BUSY`: another dog's run is still in progress. Go to Record Result with
  `result:success` and the note "skipped: another run in progress". Do NOT
  fetch, write snapshots, or run `relay`/`fail`. You are done.
- `FETCH RIV-3 RIV-5 ...`: go to Step 3 with exactly those identifiers.
  The list holds at most 6 issues (`RIV_RELAY_MAX_FETCH`), oldest change first.
  Fetch only those; any others wait for the next run, and the relay holds its
  cursor until the backlog is drained. Never fetch more than you were given.
- Exit code not 0: `relay.py` already counted the failure. Go to Record Result
  with `result:failure`.

## Step 3: Read each issue that changed

For EACH identifier after `FETCH`, call `Arcade_UseTool` on `prod-full-suite`:

```json
{"tool_name": "Linear.GetIssue",
 "inputs": {"issue_id": "RIV-3", "include_comments": true,
            "include_attachments": false, "include_children": false,
            "include_relations": false}}
```

Write the tool's JSON result, complete and unedited, to
`~/gt/.runtime/riv-relay/pending/<identifier>.json`:

```bash
cat > ~/gt/.runtime/riv-relay/pending/RIV-3.json <<'RIV_SNAPSHOT'
{"issue": {"identifier": "RIV-3", "...": "the whole result, every comment"}}
RIV_SNAPSHOT
```

Keep every comment, including ones signed `Δ Delta`; the script filters those.
If `has_more_comments` is true, or any call fails, go to Step 5.

## Step 4: Relay

```bash
python3 ~/gt/plugins/riv-relay/relay.py relay
```

It prints one summary line, e.g. `riv-relay: 1 mail(s) logged to dry-run.log
from 7 RIV issue(s)`. Exit code 0: Record Result with `result:success` and that
line. Otherwise `relay.py` already counted the failure: Record Result with
`result:failure` and its error output.

## Step 5: Report a failed read

```bash
python3 ~/gt/plugins/riv-relay/relay.py fail "<which call failed: its error>"
```

This counts the failure and escalates once, with fingerprint `riv-relay`, on
the 5th failure in a row. Go to Record Result with `result:failure`.

## Record Result

```bash
bd create "riv-relay: <summary line>" -t chore --ephemeral \
  -l type:plugin-run,plugin:riv-relay,result:<success|failure> \
  -d "<summary line or error>" --silent 2>/dev/null || true
```

Do not escalate on failure; `relay.py` owns escalation.

## What gets relayed (reference)

`relay.py` implements the convention from RIV-3:

- River's new comments, and edits to them. Comments containing `Δ Delta` are
  agent posts and are skipped.
- Description checkbox ticks, only while `needs-river` is set, after two runs
  read the same text, as a list of the boxes that flipped.
- `needs-river` removed with no River comment relayed since it was set.
- Moves to a Done or Canceled state, unless the issue's latest comment is
  signed `Δ Delta` and was posted within 10 minutes before the move. Agents
  close issues as River's user, so that comment is the only sign the move was
  theirs.

Routing, first match wins: `@phagey` / `@gigi` in the comment, then a label
`agent:<name>`, then an `Agent: monorepo/crew/<name>` line in the description,
then `monorepo/crew/gigi`. A `Bead: mo-…` line in the description is copied
into the mail. Follow-ups on the same issue reply to its first mail.

State lives in `~/gt/.runtime/riv-relay/state.json` and is written only after
each mail is sent (or logged), so a failed send is retried next run.
