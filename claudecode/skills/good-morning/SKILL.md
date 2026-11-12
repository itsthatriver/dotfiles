---
name: good-morning
description: River's morning kickoff for the phagey session. Resets the adaptive RIV + GitHub sweep to its fast cadence, runs a catch-up sweep over the overnight gap, then gives a short, ranked "what to chase first" digest of everything waiting on River (one-line decisions first, then reviews). Use when River says "good morning", "I'm back", "what's waiting on me", or invokes `/good-morning`.
allowed-tools: '*'
---

# Good Morning

Gets River from "just sat down" to "knows the first three things to do" in one message, and puts the sweep back to its daytime pace.

It reuses the phagey sweep tooling: `~/.local/share/phagey-tools/` (`next-sweep.sh`, `gh-phagey-mentions.sh`, `check-delegates.sh`) and the rules in memory `riv-sweep-includes-github-mentions` and `rules-of-engagement-i-got-it`. If those tools are missing, say so and stop: this skill is for the phagey session.

## Steps

### 1. Speed the sweep back up

- Run `~/.local/share/phagey-tools/next-sweep.sh reset`. It prints `<minutes> <cron>`.
- `CronList`. If a sweep one-shot is pending more than 15 minutes out, `CronDelete` it. Then `CronCreate` a one-shot (`recurring: false`) at the printed cron, using the standard adaptive sweep prompt, the same prompt the last sweep job used.
- If no sweep job exists at all, the chain broke. Recreate it and say so in the digest.

### 2. Catch up on the overnight gap

The cutoff is the last successful sweep. If you don't know it, use 18:00 PT the previous day. Run the normal sweep:

- the two `Linear.ListRecentComments` calls: team RIV, then no team with `body_contains: "phagey"`;
- `gh-phagey-mentions.sh <cutoff>`;
- `gt mail inbox`;
- `check-delegates.sh`.

Act on anything new exactly as a sweep would, following the rules of engagement. Anything it turns up goes at the top of the digest.

### 3. Gather what's waiting on River

Do it cheaply, in parallel:

- **Decisions:** `Linear.ListIssues` for team RIV, label `needs-river`, every state except Done and Canceled. For each one, take the one-line call to action from the newest agent comment or the description (the `Reply (recommended first)` block).
- **Reviews:** run `gh pr list --author itsthatriver --state open --json number,title,isDraft,mergeable,reviewDecision,updatedAt` for ArcadeAI/monorepo and ArcadeAI/mlops, plus `gh search prs --review-requested=itsthatriver --state=open`.
  - Keep only PRs that are ready for her: not a draft, mergeable, and not already approved by the reviewer they need.
  - Pick up the extra decisions a PR carries, such as an ops step or a default to confirm, from its READY note on the RIV item.
- **Agent blockers:** anything a polecat or crew agent is stuck on that only River can clear, e.g. a permission prompt (`check-delegates.sh` PROMPT) or a hold waiting on her.

Skip the reserved Gas Station trial items (PLT-2956, PLT-3237, PLT-2437, PLT-2895, PLT-2331) and their PRs.

### 4. Rank and write the digest

Rank by how much a minute of River's time unblocks:

1. **Blocking agents or other people.** Prompts, holds that stall a polecat, and PRs someone else is waiting to see.
2. **One-line decisions.** They're cheap and each one releases queued work. Within this tier, put the ones blocking the most first.
3. **Reviews of ready PRs.** Riskiest or most depended-on first, e.g. a contract PR before its consumers, then the oldest.
4. **FYIs.** Mention them only if there's something new.

Format, kept short (about 25 lines at most):

```markdown
Morning! Overnight: <one line: quiet / what came in / what agents finished>. Sweeps are back to every 15 min.

**Decisions (one-line replies):**
- **RIV-NN** <what it is, a few words>: `option-a` (recommended) / `option-b`
...

**Reviews:**
- **#NNNN** <what it is> <extra ask if any, e.g. "+ raise GPU cap">
...

**Blocked on you:** <only if anything is>
```

Rules for the digest:

- Every item has a link or an identifier and the exact reply that moves it forward. No item should leave River asking "what do I do with this?".
- Don't repeat background she has already seen. One clause of context per item is enough.
- If nothing is waiting, say so in one line.
