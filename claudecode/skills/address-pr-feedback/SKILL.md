---
name: address-pr-feedback
description: End-to-end pipeline for resolving PR review feedback — pulls every open review thread + CI status, categorizes by theme, presents a plan-gate for approval, applies fixes per theme with local tests, and replies on every thread. Use when working a code review round (round 2+) or before re-requesting review. Calls pr-reply-discipline for the reply phase. NOT for the initial review pass (use review).
allowed-tools: '*'
---

# Address PR Feedback

Orchestrator for the full "respond to a code review" loop. Fetches everything, groups it for the user, gets approval, applies fixes one theme at a time, replies on every thread, pushes.

**Iron Law (inherited from `pr-reply-discipline`):** every open review thread gets a reply. Addressed, declined, or answered — silence does not qualify.

## When to Use

Stop at first match:

1. PR has reviewer comments you have not yet processed → use this skill.
2. You already made the fixes by hand and just need the reply pass → use `pr-reply-discipline` directly.
3. CI is red and there is no human feedback yet → use `refresh-pr` first; come back here if reviewers add comments.
4. You are the reviewer doing the initial pass → use `review` instead.

## Phases

```
intake → triage → plan-gate (HARD STOP) → apply per theme → reply → finalize
```

### 1. Intake

Detect the PR (current branch or `<num>` argument) and pull everything in one pass:

```bash
OWNER=<owner>; REPO=<repo>; PR=<number>

# Threads (open, with comment chains)
gh api graphql -f query='
  query($owner:String!,$repo:String!,$pr:Int!){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$pr){
        reviewThreads(first:100){
          nodes{ id isResolved isOutdated path line
                 comments(first:50){ nodes{ id databaseId author{login} body diffHunk createdAt }}}}}}}' \
  -F owner="$OWNER" -F repo="$REPO" -F pr="$PR" \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)'

# Issue-level PR comments (top-level, not on a line)
gh api "repos/$OWNER/$REPO/issues/$PR/comments"

# CI status (failed checks are categorized as actionable items)
gh pr checks "$PR" --json name,state,conclusion,detailsUrl
```

Also load the diff for the current head so the planner can map thread locations to current line numbers (some threads will be outdated).

### 2. Triage

For each open thread (and each failed CI check), assign:

| Field | Values |
|---|---|
| **disposition** | `fix` / `decline` / `question` / `discuss` / `praise-ack` / `obsoleted` |
| **theme** (when `fix`) | `logic` / `tests` / `style` / `naming` / `perf` / `security` / `docs` / `out-of-scope` |
| **ci-class** (CI items) | `flake` / `lint` / `format` / `type` / `test` / `build` / `env` |

Rules:

- **Bot comments are first-class.** Treat security-scanner / codecov-drop / dependency-audit as `fix` candidates unless they are pure FYI. Allowlist nothing.
- **Outdated threads** (line moved, file gone): `disposition=obsoleted` — a brief reply explains "addressed in rebase / refactor at \<sha\>" and the thread is resolved.
- **Cross-thread conflicts**: when reviewer A asks for X and reviewer B asks for not-X on the same line, flag as `discuss` for the plan gate. Do not pick a side autonomously.
- **Out-of-scope suggestions** ("while you're in here, refactor Y"): theme = `out-of-scope`, action = file a new beads/Linear issue, reply with the issue link. Do not balloon the current PR.

### 3. Plan gate — HARD STOP

Print a structured summary and **wait for explicit approval** before changing any code. Format:

```
PR #<n> — <title>

Open threads: <N>  |  Already-replied: <K>  |  Actionable: <M>
CI failures: <C>

Themes (to fix):
  logic      <count>  — <one-line summary, list of thread IDs>
  tests      <count>  — ...
  style      <count>  — ...

Decline (with reason):
  - thread <id>: <reason>

Questions (need user input before reply):
  - thread <id>: <question>

Conflicts (reviewers disagree):
  - threads <a> vs <b>: <summary>

Out-of-scope (will file separately):
  - thread <id> → new bead suggestion: <title>

CI:
  - <check name>: <ci-class> — <one-line diagnosis or "flake → rerun">

OK to proceed? [respond with go / redirect / partial]
```

Wait for user response. Acceptable redirects: skip a theme, change a disposition, fold/split themes. Do not start changing code without explicit "go".

### 4. Apply per theme

For each accepted theme, in order — smallest blast radius first (`style` / `docs` before `logic`):

1. Make the code changes for all threads in the theme.
2. Run the **narrowest test that covers them** (file-level if possible; package-level if not). Abort the theme on red and surface the failure.
3. Stage and commit:

   ```
   Address review: <theme>

   <one-line summary>

   Threads: <id1>, <id2>, ...
   ```

One commit per theme. The thread-ID trailer lets the reply phase look up each thread's resolving SHA without keeping local state.

### 5. Reply

Delegate to `pr-reply-discipline`. For each thread:

- `fix` → "Done in \<sha\> — \<one-line what changed and why\>."
- `decline` → "\<reason in one or two sentences\>. Keeping as-is."
- `question` → "\<answer\>."
- `obsoleted` → "Addressed by rebase/refactor in \<sha\>."
- `out-of-scope` → "Filed separately as \<issue link\>. Keeping this PR focused."

Replies live on the **original thread**, never as a top-level PR comment. After replying, mark resolved where the disposition is unambiguous (`fix`, `obsoleted`, `out-of-scope`). Leave `decline` / `discuss` / `question` threads unresolved — that is the reviewer's call.

### 6. Finalize

```bash
git push --force-with-lease
gh pr checks "$PR"          # confirm CI is re-running
```

If a reviewer was previously requested and is dismissed (`requested_reviewers` cleared by GitHub when you push), re-request:

```bash
gh api -X POST "repos/$OWNER/$REPO/pulls/$PR/requested_reviewers" \
  -f reviewers="$REVIEWER"
```

Print a closing summary:

```
Addressed: <m>   Declined: <d>   Obsoleted: <o>   Filed-separately: <s>
Push: <sha>      CI: re-running (<n> checks)
Unresolved (awaiting reviewer): <count>
```

## State and resumability

Most state lives on GitHub (commits, resolved flags, reply timestamps). The skill is mostly stateless. If a run is interrupted between phases 4 and 5, re-running re-derives state from:

- `git log --grep='Threads:'` on the branch → which threads are addressed in which commit
- `gh api .../pulls/$PR/comments` → which threads already have your reply newer than your last push

No local cache required.

## Pitfalls

- **Skipping the plan gate** — the gate exists because reviewers' "obvious fix" is often wrong-by-context. The user must confirm theme groupings before code moves.
- **Folding `out-of-scope` items into the PR** — they belong in new issues, not this branch.
- **Replying as a top-level PR comment** instead of on the thread — the reviewer cannot map it back. See `pr-reply-discipline`.
- **Resolving a thread before replying** — the reviewer's notification feed shows "resolved" with no reasoning. Reply first, then resolve.
- **Treating bot comments as noise** — codecov drops and security-scan hits are real fixes. Triage them.
- **Auto-picking a side on a reviewer conflict** — surface it; let the user decide.
