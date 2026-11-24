# turn-ledger

A per-turn token ledger for the Gas Town agent fleet. Every time an agent finishes a turn, one JSON
line is appended with the turn's exact token counts, its dollar equivalent, and a rules-based label
for what the turn was for.

## What it records

One line per completed turn (a user prompt, plus everything the agent did until it stopped).
Prompt text is not stored beyond the first 80 characters (`prompt_head`).

| Field | Meaning |
|-------|---------|
| `agent`, `session_id`, `prompt_id` | `claude` or `codex`; the session; the prompt's id when the transcript has one |
| `role`, `rig`, `name` | From the working directory: `crew`, `polecat`, `mayor`, `deacon`, `dog`, `boot`, `witness`, `refinery`, else `other` |
| `ts_start`, `ts_end` | Prompt time and last model response of the turn (UTC) |
| `models` | Tokens per model: `input`, `output`, `cache_write_5m`, `cache_write_1h`, `cache_read` |
| `usd_equiv` | Dollar equivalent of `models` plus `subagent_models`, from the analysis price table |
| `subagent_usd`, `subagent_models`, `subagent_api_calls` | Subagent usage whose timestamps fall inside the turn |
| `api_calls`, `cold_calls`, `ctx_max` | Model calls; calls more than 5 minutes after the previous call; largest context |
| `prompt_kind`, `subtype`, `tool_sig`, `issue_refs` | Prompt origin; plugin name; histogram of tool-call kinds; `RIV-123`, `PLT-12`, `#123` found in the prompt |
| `goal`, `goal_rule`, `goal_conf` | Label, the rule that picked it (ids match the 2026-11-24 analysis), `high` or `low` |
| `unpriced_models` | Models with tokens but no price (every Codex model today, so Codex `usd_equiv` is 0) |

Token counts are exact: usage is summed per `message.id`, taking the largest value of each field
across the streaming repeats of a message.

## Where

`~/gt/.runtime/turn-ledger/YYYY-MM-DD.jsonl`, dated by the UTC date the turn ended. Set
`TURN_LEDGER_HOME` to use another directory. Next to the ledger:

- `cursors/<session_id>.json`: where each session's next unfinished turn starts.
- `errors.log`: every hook failure, with event, session id and traceback. The hook always exits 0,
  so look here when records are missing.

## Install

Run from the checkout the hooks should point at (the commands embed the script's absolute path):

```bash
python3 gastown/turn-ledger/turn_ledger.py install-hooks          # ~/.gt/hooks-base.json
python3 gastown/turn-ledger/turn_ledger.py install-codex-hooks    # ~/.codex/hooks.json
```

Each takes an optional path argument. Each is idempotent, writes `<file>.bak` before its first
change, and leaves existing entries alone. Claude gets `Stop` and `SessionStart` (both async) and
`SessionEnd`; Codex gets `Stop` and `SessionStart`.

## Read

Dollar equivalent by goal:

```bash
cat ~/gt/.runtime/turn-ledger/*.jsonl | jq -s 'group_by(.goal) | map({goal: .[0].goal, usd: (map(.usd_equiv) | add)}) | sort_by(-.usd)'
```

The same, by role, in Python:

```python
import collections, glob, json, os

usd = collections.Counter()
for path in glob.glob(os.path.expanduser("~/gt/.runtime/turn-ledger/*.jsonl")):
    for line in open(path):
        record = json.loads(line)
        usd[(record["role"], record["goal"])] += record["usd_equiv"]
print(usd.most_common(10))
```

## How a turn is closed

A hook run is not a turn. Each run reads the session's transcript from its cursor and closes every
turn it can prove is finished, then moves the cursor to the first turn still open:

- A turn starts at a user record with text content; `tool_result` records do not start one.
- A turn is finished once a later turn has started, or when its last assistant message stopped for a
  reason other than `tool_use`. `SessionEnd` flushes whatever is left.
- A per-session `fcntl` lock keeps overlapping async runs from double-appending.

## Known limits

- A resumed session that replays old messages into a new transcript file is counted again under the
  new session id.
- A subagent that outlives its parent turn (background agents) is not attributed to any turn.
- If the process dies between appending lines and saving the cursor, the next run repeats those
  lines. `session_id` plus `ts_start` identifies a turn if you need to dedupe.

## Develop

```bash
python3 gastown/turn-ledger/test_turn_ledger.py     # or: pytest gastown/turn-ledger
ruff check gastown/turn-ledger && ruff format gastown/turn-ledger
```

The rules in `goals.py` are ported from the phagey token analysis
(`~/.local/share/phagey/analysis-2026-11-24/tokens/`).
