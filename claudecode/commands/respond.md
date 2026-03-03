---
description: Commit, push, and reply to addressed PR review threads
---

# Respond

After addressing review feedback: commit, push, and reply to the threads that were resolved by
the new changes. Do NOT resolve threads — that is the reviewer's prerogative.

## Instructions

### 1. Commit and Push

Stage and commit current changes:

```bash
git status --short
git add -p   # stage interactively, or stage specific files if unambiguous
```

Write a commit message that references the review feedback addressed (e.g., "address review: ...").

```bash
git push -u origin HEAD
```

Capture the commit SHA:

```bash
git rev-parse HEAD
```

### 2. Identify Changed Files

```bash
git diff HEAD~1..HEAD --name-only
```

### 3. Fetch Unresolved Review Threads

Use the same GraphQL query as `/review-pr`:

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

Filter to threads where `isResolved == false`.

### 4. Match Threads to Changes

For each unresolved thread:

1. Check if `thread.path` is in the list of changed files
2. If yes, read the thread comment body and the diff hunk for that file/line
3. Determine semantically whether the commit addresses the feedback

Only reply to threads that are clearly addressed by the new commit. Skip threads where:
- The file wasn't changed
- The change doesn't address the specific feedback

### 5. Reply to Addressed Threads

For each thread that was addressed, post a reply using the REST endpoint
(requires `databaseId` from the GraphQL response — this bridges GraphQL reads to REST writes):

```bash
gh api \
  repos/{owner}/{repo}/pulls/{pr_number}/comments/{comment_databaseId}/replies \
  -X POST \
  -f body="Addressed in {commit_sha}: <brief description of what was changed>"
```

### 6. Report

```text
Commit:    <sha>  <message>
Replied:   N threads
  - path/to/file.go:42 (@reviewer)
  - path/to/other.go:17 (@reviewer)
Skipped:   M threads (not addressed by this commit)
Remaining: K unresolved threads total
```
