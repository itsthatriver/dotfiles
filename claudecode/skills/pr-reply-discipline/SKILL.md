---
name: pr-reply-discipline
description: Iron-law reply discipline for PR review threads — every open thread gets a reply (addressed, dismissed, or answered); silence does not qualify. Use directly when fixes are already made and you need to post threaded replies, or when manually marking specific threads resolved. Called as the reply phase of address-pr-feedback (the orchestrator for the full review-resolution pipeline). NOT for the initial review pass (use review).
allowed-tools: '*'
---

# PR Reply Discipline

Every review thread gets a reply. Addressed and dismissed both qualify. Silence does not.

**Iron Law:** NO REVIEW THREAD CLOSED OR LEFT OPEN WITHOUT A REPLY ON THE ORIGINAL THREAD.

## When to Use

Answer IN ORDER. Stop at first match:

1. Pushing a commit in response to PR review comments? → Use this skill.
2. Reviewer left feedback you intend to dismiss as not-an-issue? → Use this skill.
3. About to mark a review thread resolved? → Use this skill (verify the reply first).
4. Doing the initial review (you are the reviewer)? → Use the `review` skill instead.

## Why this discipline

Reviewers who don't see a reply assume the comment was missed. They re-raise it on the next round, or the thread silently rots. Dismissing without a reply is worse: the reviewer can't tell whether you considered the point and disagreed, or never saw it.

The reply lives on the **original thread** — not a top-level PR comment, not a commit message, not the PR description. That is where the reviewer is looking.

## Workflow

### 1. Enumerate open threads

Identify the repo and PR number, then list unresolved review threads:

```bash
OWNER=<owner>; REPO=<repo>; PR=<number>

# Threads (with resolved state)
gh api graphql -f query='
  query($owner:String!,$repo:String!,$pr:Int!){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$pr){
        reviewThreads(first:100){
          nodes{ id isResolved comments(first:20){ nodes{ id author{login} body path line createdAt }}}
        }
      }
    }
  }' -F owner="$OWNER" -F repo="$REPO" -F pr="$PR" \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[] | select(.isResolved==false)'
```

For per-comment listing (REST):

```bash
gh api "repos/$OWNER/$REPO/pulls/$PR/comments" --jq '.[] | {id, path, line, user: .user.login, body}'
```

### 2. Per thread, decide and act

For each open thread:

- **Address** — make the code change locally, commit, push. Note the resulting SHA.
- **Dismiss** — articulate the reason in one or two sentences before replying.

Group changes into coherent commits where it makes sense; one commit per thread is fine but not required.

### 3. Reply on the original thread

The reply belongs on the same thread the reviewer opened. Use the comment ID from step 1.

**Address** — reply with the resolving commit SHA:

```bash
gh api -X POST "repos/$OWNER/$REPO/pulls/$PR/comments/$COMMENT_ID/replies" \
  -f body="Done in <commit-sha>."
```

**Dismiss** — reply with reasoning, then mark resolved if appropriate:

```bash
gh api -X POST "repos/$OWNER/$REPO/pulls/$PR/comments/$COMMENT_ID/replies" \
  -f body="Disagree because <reason>. Keeping as-is."
```

Reply form is free; the recommended patterns above are reply-friendly. The reviewer should be able to read the reply alone — without re-reading the thread above — and know the disposition.

### 4. Verify before marking the round complete

Confirm every open thread has a reply newer than your last push (or a dismissal):

```bash
gh api graphql -f query='
  query($owner:String!,$repo:String!,$pr:Int!){
    repository(owner:$owner,name:$repo){
      pullRequest(number:$pr){
        reviewThreads(first:100){
          nodes{ id isResolved comments(last:1){ nodes{ author{login} createdAt }}}
        }
      }
    }
  }' -F owner="$OWNER" -F repo="$REPO" -F pr="$PR" \
  --jq '.data.repository.pullRequest.reviewThreads.nodes[]
        | select(.isResolved==false and (.comments.nodes[0].author.login != "<your-gh-login>"))
        | .id'
```

If anything comes back, you have un-replied open threads. Reply before re-requesting review.

### 5. Then re-request or resolve

Only after step 4 returns nothing:

- Re-request review (`gh api -X POST repos/$OWNER/$REPO/pulls/$PR/requested_reviewers …`) if the reviewer should look again.
- Resolve threads where the reviewer indicated "ack" or where the dismissal stands and they're unlikely to push back.

## Pitfalls

- **Top-level PR comments instead of thread replies** — a reviewer can't easily map "I addressed all your comments" back to specific threads. Reply per thread.
- **Commit message instead of reply** — reviewers don't read commit messages while triaging review threads. Reply.
- **Silent push** — pushing a follow-up commit without a reply leaves the thread in "needs response" state in the reviewer's mental model.
- **Resolving without replying** — the reviewer's notification feed shows "resolved" with no reasoning. Always reply, then resolve.
- **Bulk-dismissal without per-thread reasoning** — even when several threads share a reason ("we discussed this in Slack and decided X"), reply on each thread.

## Future: enforcement

This skill teaches the discipline. A future extension to the `done` skill (or refinery's pre-merge gate) could refuse to close or merge while open review threads have no agent reply newer than the last push. That's a follow-up; not part of this skill.
