---
description: Analyze git history for risk signals — churn hotspots, bus factor, bug clusters, velocity, firefighting rate
---

# Repo Risk

Analyze the repository's git history to surface risk signals, then prompt for a decision on what to address.

## Instructions

### 1. Locate the Source Root

Run from the current working directory. If an `app/` or `src/` subdirectory exists, run churn and bug-cluster commands from there to avoid noise from lockfiles and generated code.

```bash
REPO_ROOT=$(git rev-parse --show-toplevel 2>/dev/null || pwd)
REPO_NAME=$(basename "$REPO_ROOT")

if [ -d "$REPO_ROOT/app" ]; then
  SRC_DIR="$REPO_ROOT/app"
elif [ -d "$REPO_ROOT/src" ]; then
  SRC_DIR="$REPO_ROOT/src"
else
  SRC_DIR="$REPO_ROOT"
fi
```

### 2. Run the Five Signals

Run all five commands and capture their output. Label each section clearly.

**Signal 1 — High-churn files (most modified in the last year):**

```bash
cd "$SRC_DIR"
git log --format=format: --name-only --since="1 year ago" \
  | sort | uniq -c | sort -nr | head -20
```

**Signal 2 — Contributors and bus factor:**

```bash
cd "$REPO_ROOT"
git shortlog -sn --no-merges
```

**Signal 3 — Bug-cluster files (files mentioned in fix/bug commits):**

```bash
cd "$SRC_DIR"
git log -i -E --grep="fix|bug|broken" --name-only --format='' \
  | sort | uniq -c | sort -nr | head -20
```

**Signal 4 — Monthly commit velocity (full history):**

```bash
cd "$REPO_ROOT"
git log --format='%ad' --date=format:'%Y-%m' | sort | uniq -c
```

**Signal 5 — Firefighting frequency (last year):**

```bash
cd "$REPO_ROOT"
git log --oneline --since="1 year ago" \
  | grep -iE 'revert|hotfix|emergency|rollback' || echo "(none found)"
```

### 3. Cross-Reference Churn + Bug Clusters

Compare the file lists from Signal 1 and Signal 3. Files appearing on **both** lists are the highest-risk code — they change constantly AND accumulate defects, indicating recurring patches rather than root-cause fixes.

### 4. Assess Each Signal

**Churn hotspots:**

- Files with dramatically more changes than peers warrant investigation
- Note whether high-churn files are also in bug clusters (critical risk)

**Bus factor:**

- Single author > 60% of commits → high organizational risk
- Top historical contributors absent from recent months (check last 90 days vs all-time) → knowledge loss

**Bug clusters:**

- Files frequently touched in bug commits are candidates for deeper test coverage or refactoring
- Overlap with churn list = critical; bug-only = moderate

**Velocity:**

- Steady month-over-month: healthy
- Sharp drop in a specific month: team event (departure, reorg)
- Declining trend: momentum loss or project wind-down
- Periodic spikes only: batched releases, not continuous shipping

**Firefighting:**

- 0-2 reverts/year: normal
- 1+ per month: deploy process or testing gap
- 0 found with poor commit discipline: inconclusive

### 5. Output the Risk Report

```markdown
## Repo Risk Report — {REPO_NAME} — {date}

### Critical Risk (high churn AND bug cluster)
Files on both lists — recurring patches, not fixes:
- {file} — {churn count} changes, {bug count} bug commits

### Code Hotspots (high churn only)
- {file} — {count} changes in the last year

### Bug Clusters (recurring defects)
- {file} — {count} bug-related commits

### Bus Factor
- Top author: {name} ({N}% of all commits)
- Contributors active in last 90 days: {N}
- Knowledge risk: {low/moderate/high} — {reason}

### Velocity Trend
- Trend: {accelerating / stable / declining / erratic}
- Notable: {any sharp drops or spikes with likely cause}

### Firefighting Rate
- {N} reverts/hotfixes in the last year
- Assessment: {normal / elevated / concerning}

---

### Suggested Actions

| Finding | Suggestion |
|---------|-----------|
| Critical risk files | Refactor to reduce scope; add test coverage before next change |
| High bus factor | Schedule knowledge transfer; add runbooks or ADRs for key areas |
| Bug cluster (no churn overlap) | Add regression tests; investigate root cause pattern |
| Declining velocity | Investigate cause; surface to team |
| Elevated firefighting | Review deploy process; add staging gates or feature flags |
```

### 6. Prompt for Decision

After presenting the report, ask:

> Which of these risk areas would you like to address first? Options:
>
> 1. Investigate a specific file or area in depth
> 2. Draft a refactoring plan for a critical risk file
> 3. Identify test coverage gaps for bug-cluster files
> 4. Generate a knowledge-transfer checklist for bus factor risks
> 5. Something else

Wait for the user's choice before proceeding.
