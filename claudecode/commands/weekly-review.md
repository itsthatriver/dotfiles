---
description: Analyze session logs and propose tooling/methodology improvements
---

# Weekly Review

Analyze the past week's agent sessions and generate improvement proposals.

## Instructions

### 1. Gather Data

Read session logs from the last 7 days:

```bash
find ~/.claude/session-logs/ -name '*.md' -mtime -7 -type f | sort
```

If a knowledge index tool is available (via MCP), also search for additional context:
- Search for recent session summaries
- Search for patterns in past interactions

### 1b. Git Log Fallback

If session logs lack transcript content (no prompts, tools, or files sections), supplement with git history from known project directories:

```bash
# Check common project roots for recent commits by the current user
for dir in ~/src/*/ ~/work/*/; do
  if [ -d "$dir/.git" ]; then
    commits=$(git -C "$dir" log --oneline --after="7 days ago" --author="$(git config user.name)" 2>/dev/null)
    if [ -n "$commits" ]; then
      echo "=== $(basename $dir) ==="
      echo "$commits"
      echo
    fi
  fi
done
```

Use commit messages to infer work patterns (files touched, types of changes, project focus areas) when session logs are metadata-only.

### 2. Analyze Patterns

For each session log, extract:
- **Prompt patterns**: What kinds of requests are being made?
- **Tool usage**: Which tools are used most? Which are underused?
- **Files modified**: What areas of codebases get the most attention?
- **Duration**: How long are sessions? Are some types faster than others?
- **Work levels**: Distribution of patch/task/feature work

### 3. Identify Improvements

Look for:

| Signal | Proposal Type |
|--------|--------------|
| Same prompt structure repeated 3+ times | Suggest a slash command or automation |
| Debugging cycles > 3 attempts | Suggest tooling or CLAUDE.md refinement |
| Frequent edits to same file types | Suggest linter rule or pre-commit hook |
| Long sessions with many tool calls | Suggest breaking into smaller tasks |
| Patterns of poor agent output | Suggest CLAUDE.md instruction additions |
| Manual steps that could be automated | Suggest hook or script |

### 4. Output Format

```markdown
## Weekly Agent Review — {date range}

### Session Summary
- **Sessions**: N total
- **Duration**: N hours total, avg M minutes/session
- **Work levels**: N patches, N tasks, N features
- **Top tools**: Edit (N), Bash (N), Grep (N)

### Improvement Proposals

#### 1. [Proposal Title]
**Signal**: What pattern was observed
**Suggestion**: What to change (CLAUDE.md, hook, command, tooling)
**Impact**: Expected improvement
**Effort**: Low/Medium/High

#### 2. [Proposal Title]
...

### Prompt Quality Notes
- Prompts that worked well: [examples]
- Prompts that could be improved: [examples with suggestions]

### Next Actions
- [ ] Action item 1
- [ ] Action item 2
```
