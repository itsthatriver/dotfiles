+++
name = "phagey-sweep"
description = "Cheap 30-minute check that wakes phagey by gt mail only when River's comments, GitHub mentions, or machine health need judgement"
version = 1

[gate]
type = "cooldown"
duration = "30m"

[tracking]
labels = ["plugin:phagey-sweep", "category:relay"]
digest = true

[execution]
timeout = "6m"
notify_on_failure = false
severity = "medium"
+++

# phagey Sweep

Replaces phagey's hourly Opus sweep. This plugin looks for anything that needs
phagey's judgement and mails phagey once if it finds some. If it finds nothing,
nobody is woken and nothing is spent.

You (the dog) do the one thing only an LLM session can do: read Linear through
the Arcade gateway and hand the raw JSON to `sweep.py`. The script decides
everything else: the cursor, which comments count, GitHub, machine health, what
was already reported, who gets mailed, and when to escalate. Do not make those
decisions yourself, and do not summarize, filter or edit what you read.

**Dry run.** Until `~/gt/.runtime/phagey-sweep/DELIVER` exists, `sweep.py`
writes the mail it would send to `~/gt/.runtime/phagey-sweep/dry-run.log` and
sends nothing. Do not create or remove that file.

**Not RIV.** `riv-relay` already relays River's comments on team RIV. The
script drops RIV comments from both feeds; do not add a RIV read.

## Rules

- Read Linear ONLY through the `prod-full-suite` MCP server's `Arcade_UseTool`,
  and call ONLY `Linear.ListRecentComments`. Never write to Linear.
- If a tool answers with an authorization link or asks you to sign in, do NOT
  follow it. Treat it as a failed read (Step 4).
- Never run `gt mail send` or `gt escalate` yourself. `sweep.py` does the mailing.
- Never run GitHub, disk, refinery or delegate checks yourself. `sweep.py` does.

## Step 1: Begin

```bash
python3 ~/gt/plugins/phagey-sweep/sweep.py begin
```

- `BUSY`: another dog's run is still in progress. Go to Record Result with
  `result:success` and the note "skipped: another run in progress". Do NOT
  read, ingest, run or fail. You are done.
- `CURSOR <timestamp>`: use that timestamp as `created_after` below.
- Exit code not 0: `sweep.py` already counted the failure. Go to Record Result
  with `result:failure`.

## Step 2: Read team PLT

Call `Arcade_UseTool` on `prod-full-suite` with:

```json
{"tool_name": "Linear.ListRecentComments",
 "inputs": {"team": "PLT", "created_after": "<the CURSOR timestamp>", "limit": 25}}
```

Hand each page to the script, complete and unedited, right after you read it:

```bash
python3 ~/gt/plugins/phagey-sweep/sweep.py ingest plt <<'PHAGEY_PAGE'
{"comments": ["...the whole result, every comment..."], "pagination": {"has_next_page": false}}
PHAGEY_PAGE
```

If the page has `pagination.has_next_page: true`, call the tool again with
`"end_cursor"` set to `pagination.end_cursor`, up to 4 pages in all. Stop after
4 even if more remain; the script notes it in the mail.

If a call fails, or `ingest` exits with a code other than 0 (`sweep.py`
already counted that failure), go to Step 4 for the former or Record Result
with `result:failure` for the latter.

## Step 3: Read phagey's handle everywhere else

Same tool, no team, so project and document comments are included:

```json
{"tool_name": "Linear.ListRecentComments",
 "inputs": {"body_contains": "phagey:", "created_after": "<the CURSOR timestamp>", "limit": 25}}
```

Hand each page over with `sweep.py ingest handle`, exactly as in Step 2, with
the same paging rule. Then run:

```bash
python3 ~/gt/plugins/phagey-sweep/sweep.py run
```

It prints one summary line, e.g. `phagey-sweep: 2 item(s) sent` or
`phagey-sweep: nothing to report`. Exit code 0: Record Result with
`result:success` and that line. Otherwise `sweep.py` already counted the
failure: Record Result with `result:failure` and its error output.

If a Step 3 call fails, go to Step 4.

## Step 4: Report a failed read

```bash
python3 ~/gt/plugins/phagey-sweep/sweep.py fail "<which call failed: its error>"
```

This counts the failure and releases the run lease. On the 3rd failure in a
row it mails phagey. Go to Record Result with `result:failure`.

## Record Result

```bash
bd create "phagey-sweep: <summary line>" -t chore --ephemeral \
  -l type:plugin-run,plugin:phagey-sweep,result:<success|failure> \
  -d "<summary line or error>" --silent 2>/dev/null || true
```

Do not escalate on failure; `sweep.py` owns that.

## What wakes phagey (reference)

One mail to `monorepo/crew/phagey`, subject `phagey-sweep: N items`. For each
item the body gives the source, the issue or PR, a URL, the author and the first
300 characters. Sources:

- **Linear PLT:** River's comments on team PLT.
- **Linear phagey::** River's comments anywhere else that contain `phagey:`.
  Comments on team RIV are left to `riv-relay`.
- **GitHub:** every line `~/.local/share/phagey-tools/gh-phagey-mentions.sh`
  prints for the cursor window.
- **Health:** free space on `/System/Volumes/Data` under 60 GiB
  (`PHAGEY_SWEEP_MIN_DISK_GIB`), the monorepo refinery running (phagey's
  standing rule is that it stays off), and anything
  `~/.local/share/phagey-tools/check-delegates.sh` flags.

River's email is read at run time from `git -C ~/dotfiles config user.email`
(or `PHAGEY_SWEEP_RIVER_EMAIL`). Comments signed `Δ Delta` are agent posts and
are skipped, because agents post under River's account.

A health problem is mailed when it first appears and again after 6 hours if it
persists, so a stuck problem doesn't mail every 30 minutes. A comment or mention
is mailed once.

State lives in `~/gt/.runtime/phagey-sweep/state.json` and is written only after
the mail is sent (or logged), so a failed send is retried next run. The cursor
trails the run start by 5 minutes and holds still while the GitHub read is
failing. After 3 failures in a row (a failed Linear read, a rejected page, or a
failing GitHub read) the script mails phagey once.
