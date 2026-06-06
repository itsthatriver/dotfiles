---
name: refresh-pr
description: Rebase a PR onto its upstream base, run local quality gates (lint, format, type-check, unit tests), push, then watch CI and fix failing checks to green. Use when a PR has fallen behind base, has red CI, or both. Conflict resolution is intent-driven, not merge-strategy-driven — stops and asks for help on any conflict where the upstream commit's intent is unclear.
allowed-tools: '*'
---

# Refresh PR

Bring a PR back to a publishable state: up-to-date with its base, all local quality gates green, all CI checks green.

**Core rule for rebasing:** the index for resolving conflicts is **intent**, not a git merge strategy. Each upstream commit landed on `main` (or the base branch) for a reason. That reason must survive the rebase. If you cannot read an upstream commit's intent from its message + diff, or you cannot tell whether your change would undo it, **STOP and ask the user**. Do not pick `--ours` or `--theirs` to make the conflict go away.

## When to Use

Stop at first match:

1. PR is behind base AND has red CI → use this skill.
2. PR is behind base, no CI red yet → use this skill (rebase will likely trigger CI).
3. PR is up-to-date but CI is red → use this skill (skip to phase 4).
4. PR has reviewer feedback to process → use `address-pr-feedback` (it calls `refresh-pr` first if branch is stale).
5. Brand-new PR that has never run CI → just push; this skill is for refreshing, not first-time setup.

## Phases

```
intake → sync (rebase) → local quality gate → push → ci watch → ci triage + fix loop → done
```

### 1. Intake

Detect PR + base branch. Read current state:

```bash
OWNER=<owner>; REPO=<repo>; PR=<number>

# Base branch and head SHA
gh pr view "$PR" --json baseRefName,headRefName,headRefOid,mergeStateStatus
BASE=$(gh pr view "$PR" --json baseRefName --jq .baseRefName)

# Ahead/behind
git fetch origin "$BASE" --quiet
git rev-list --left-right --count "origin/$BASE...HEAD"
# → "<behind>\t<ahead>"

# Current CI status
gh pr checks "$PR" --json name,state,conclusion,detailsUrl

# Working-tree state — must be clean before rebase
git status --porcelain
```

Refuse to proceed with a dirty working tree. Have the user commit or stash first.

### 2. Sync (rebase) — intent-driven

```bash
git fetch origin "$BASE" --quiet
git rebase "origin/$BASE"
```

If the rebase completes without conflicts, move to phase 3.

**On a conflict:**

1. List the upstream commits being replayed against:

   ```bash
   git log --oneline "HEAD..origin/$BASE"
   ```

2. For each commit involved in the conflicting hunk (use `git log -p -- <path>` to see which touched the file), read the commit message **and** the diff. What was that commit trying to achieve?
3. For each conflict region, ask: **does our change preserve the upstream commit's intent and outcome?** Three outcomes:
   - **Yes, our change is compatible with their intent** — write the combined resolution by hand, run a syntax check on the file, then `git add` and continue.
   - **No, our change would undo or break their intent** — adapt our change so the upstream intent is preserved AND our intent is preserved. If both cannot be preserved, stop.
   - **Unclear from the commit message and diff** — STOP. Surface the conflict region, the upstream commit's message, and the upstream commit's diff to the user. Ask for guidance.

**Trivial-looking cases that still need intent verification:**

- **Lockfile churn** (package-lock, Cargo.lock, go.sum, uv.lock) — regenerate from the project manifest rather than picking sides. The intent of an upstream lockfile bump is "we pinned this dependency at version X"; preserve that by re-running the package manager and confirming the upstream pin is present.
- **Generated files** — regenerate from source rather than merging text.
- **Import-order / formatter-only conflicts** — run the project's formatter; verify it produces a deterministic result that doesn't undo upstream changes.
- **Whitespace-only conflicts** — still read the upstream commit; sometimes whitespace changes encode meaningful structure (table alignment, intentional indent change). Don't `-Xignore-all-space` blindly.

**Forbidden shortcuts:**

- `git rebase -X theirs` / `-X ours` — picks sides without reading intent.
- `git checkout --theirs <file>` / `--ours <file>` — same problem.
- `git rebase --skip` to make a conflict go away — drops the upstream commit's effect or our effect, silently.

If you reach for any of these, that is the signal to stop and ask.

After resolution: `git rebase --continue`. If the rebase replay fails any subsequent commit, repeat the process for that one.

### 3. Local quality gate

Run these in order; stop on the first failure and fix locally before pushing.

```bash
# Detect the project's test interface — prefer Makefile targets, fall back to per-language tools.
if [ -f Makefile ] && grep -qE '^(check|test):' Makefile; then
    make check && make test
else
    # Fall back per detected language. Run only what applies.
    [ -f package.json ]    && { npm run lint && npm run typecheck && npm test; }
    [ -f Cargo.toml ]      && { cargo fmt --check && cargo clippy -- -D warnings && cargo test; }
    [ -f go.mod ]          && { golangci-lint run && go test ./...; }
    [ -f pyproject.toml ]  && { uv run ruff check && uv run pyright && uv run pytest; }
fi
```

Coverage classes to run (in order, cheapest first):

1. **Format check** — `cargo fmt --check`, `prettier --check`, `gofmt -l`, `ruff format --check`
2. **Lint** — `golangci-lint`, `eslint`, `clippy`, `ruff check`
3. **Type-check** — `tsc --noEmit`, `mypy`, `pyright`, `go vet`
4. **Unit tests** — language-native test runner

Failures: fix locally, re-run the failed stage and all earlier stages, then advance. Do not push with a known-broken local stage — CI will just rediscover it slower.

If a local gate fails on code you did not change (only upstream changes triggered it), that is a signal the rebase resolution mishandled intent. Re-examine the conflicting commits.

### 4. Push

```bash
git push --force-with-lease
```

`--force-with-lease` refuses the push if the remote has new commits you do not have locally (someone else pushed) — this is the safe alternative to `--force`. If it fails:

- `git fetch origin <branch>` and inspect what the other party added.
- If their push is real work that should stay, decide whether to rebase onto it or merge it; otherwise resolve and retry with another `--force-with-lease`.

### 5. CI watch

```bash
gh pr checks "$PR" --watch --interval=20
```

If checks take more than ~5 minutes, do not busy-wait — use `ScheduleWakeup` to come back when they should be done.

### 6. CI triage + fix loop

For each failed check after CI completes:

```bash
# Get the run for this branch
RUN_ID=$(gh run list --branch "$(git branch --show-current)" --limit 1 --json databaseId --jq '.[0].databaseId')

# Inspect the failure
gh run view "$RUN_ID" --log-failed | head -200
```

Classify each failure:

| Class | Signal | Action |
|---|---|---|
| `flake` | Test passed historically, log shows timing / network / retry markers | `gh run rerun "$RUN_ID" --failed`; if it flakes twice, treat as real |
| `lint` | Linter rule violation | Fix locally, push |
| `format` | Formatter would change files | Run formatter locally, push |
| `type` | Type-check error | Fix locally, push |
| `test` | Unit/integration test failure | Reproduce locally, fix, push |
| `build` | Compile/build error | Reproduce locally, fix, push |
| `env` | Missing secret, infrastructure outage | Surface to user — not a code fix |

**Fix loop is capped at 3 iterations.** Each iteration: fix → re-run local gates → push → re-watch CI. If after 3 iterations CI is still red on the same class of failure, stop and escalate to the user with a diagnosis.

### 7. Done

```bash
gh pr checks "$PR" --json state,conclusion --jq 'all(.state == "COMPLETED" and .conclusion == "SUCCESS")'
gh pr view "$PR" --json mergeStateStatus
```

Print:

```
Rebased onto: origin/<base> at <sha>
Local gates:  passed
Pushed:       <head-sha>
CI:           green (<n> checks)
Status:       <mergeable | conflicting | behind | blocked>
```

## Coupling with `address-pr-feedback`

`address-pr-feedback` calls `refresh-pr --rebase-only` at intake when the branch is behind base, so review comments map to current line numbers before triage. `refresh-pr` is also useful on its own when there is no human feedback yet — just a stale or red PR.

## Pitfalls

- **Resolving a conflict with `-X theirs` to make it disappear.** That is the failure mode this skill exists to prevent. If you can't justify the resolution in terms of upstream intent, stop.
- **Pushing with red local gates** to "let CI tell me what's wrong." CI is slower than a local run and burns reviewer attention. Fix locally first.
- **Treating a flake as a real failure and over-fixing the test.** Two consecutive failures of the same test on the same commit promote it from flake to real.
- **Looping forever on CI fixes.** The 3-iteration cap exists for a reason — if the third fix didn't take, the diagnosis is probably wrong, not the fix.
- **Forgetting `--force-with-lease`** — plain `--force` can silently overwrite someone else's push on a shared branch.
