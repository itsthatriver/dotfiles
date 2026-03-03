---
description: Commit, push, and open/update PR with Linear issue reference
---

# Ship

Deliver current branch changes: lint, commit, push, and create or update the PR.

## Instructions

### 1. Find Linear Issue ID

Graduated discovery — stop at first match:

1. **User argument**: if `/ship TEAM-123` was provided, use that ID
2. **Conductor context**: check `.context/attachments/` for files matching `[LINEAR]-*.md`
   (filename pattern: `[LINEAR]-TEAM-123.md`, heading: `# TEAM-123: Title`) — extract the ID
3. **Branch name**: parse current branch with `git rev-parse --abbrev-ref HEAD` for pattern
   `[a-zA-Z]+-[0-9]+` (e.g., `user/PLT-123-description` → `PLT-123`)
4. **Ask the user**: if none of the above yield an ID, ask — do not silently skip

### 2. Lint

Run `/lint` to auto-fix formatting before committing.

### 3. Commit Uncommitted Changes

Stage and commit any uncommitted changes:

```bash
git status --short
git add -p   # stage interactively, or stage specific files if unambiguous
```

Write a descriptive commit message following existing commit style in `git log --oneline -10`.

### 4. Push

```bash
git push -u origin HEAD
```

### 5. Create or Update PR

Check if a PR already exists:

```bash
gh pr view --json url,body 2>/dev/null
```

**If no PR exists** — create one:

```bash
gh pr create \
  --title "<descriptive title>" \
  --body "$(cat <<'EOF'
## Summary
<bullet points describing changes>

Closes TEAM-123

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
```

**If PR exists** — check whether `Closes TEAM-123` is already in the body. If not, append it:

```bash
gh pr edit --body "$(gh pr view --json body -q .body)

Closes TEAM-123"
```

### 6. Report

Output:

```text
Branch:    <branch-name>
PR:        <url>  (created | updated)
Linear:    TEAM-123
```
