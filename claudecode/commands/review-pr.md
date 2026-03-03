---
description: Fetch unresolved PR review threads and present an action plan
---

# Review PR

Fetch all unresolved review threads on the current PR, group by file, and propose an action plan.

## Instructions

### 1. Find the PR

```bash
gh pr view --json number,url,headRefName
```

If no PR exists for the current branch, stop and report: "No open PR found for this branch."

### 2. Fetch Unresolved Review Threads

Use the GitHub GraphQL API to get review threads with `isResolved` status (not available via REST):

```bash
gh api graphql -f query='
query($owner: String!, $repo: String!, $pr: Int!) {
  repository(owner: $owner, name: $repo) {
    pullRequest(number: $pr) {
      reviewThreads(first: 100) {
        nodes {
          id
          isResolved
          isOutdated
          path
          line
          comments(first: 10) {
            nodes {
              databaseId
              author { login }
              body
              createdAt
            }
          }
        }
      }
    }
  }
}
' -f owner="{owner}" -f repo="{repo}" -F pr={pr_number}
```

Resolve `{owner}`, `{repo}`, and `{pr_number}` from `gh pr view --json number` and
`gh repo view --json owner,name`.

### 3. Filter

Keep only threads where `isResolved == false`.

If no unresolved threads remain, report: "No unresolved review threads. Ready to merge."

### 4. Present Threads Grouped by File

For each file with unresolved threads, list:

```text
## path/to/file.go

### Thread 1  [line 42]  @reviewer  2026-01-15
> comment body text here
Status: active | outdated
```

### 5. Action Plan

After presenting all threads, categorize each as one of:

- **Fix** — code change needed
- **Discuss** — needs clarification or disagreement
- **Already addressed** — the change was already made

Present a numbered action plan:

```text
## Action Plan

1. [Fix] path/to/file.go:42 — <brief description of fix needed>
2. [Discuss] path/to/other.go:17 — <question to resolve>
3. [Already addressed] path/to/third.go:8 — <note on what was done>
```

### 6. Wait

Stop and wait for user approval before making any code changes.
