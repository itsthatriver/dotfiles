# Rules of Engagement for Work Items

These apply to every agent, and every person, acting on River's work items: Linear issues
(RIV, PLT, TOO and the rest), pull requests and their review threads, beads, and mail.

## I Got It

Whoever is responsible for an outcome owns it until it's done. They drive it to
completion, either by doing the work or by delegating it and following through, and they
communicate proactively so nobody has to ask for an update. Delegating work never
delegates the outcome: agents can stop without noticing, by crashing, getting stuck at a
prompt or hitting a context limit, so whoever hands work out stays accountable for it
until it's finished.

If someone looking at a ticket has to wonder "is anyone on this?" or "has the automation
broken?", we've failed, even if the work is going fine.

**Every post costs River attention.** Communicating well means River can see who has the
ball and what's waiting on her. It doesn't mean narrating the work. Post when the post
changes what someone should do next. Otherwise, record it in the bead or the PR's Status
line.

## The rules

1. **Acknowledge once, where the ask was made.** The agent that owns the work posts one
   line on the issue, comment thread or PR thread: what will happen, who is doing it, and
   what "done" looks like. A dispatcher that hands the work on doesn't post a second ack,
   and neither does a restarted session, unless the owner changes. Mail between agents
   doesn't count, because River can't see it.
2. **Post a state change only when it changes who has the ball.** That means:
   - READY, once per head SHA, on the PR;
   - blocked on a decision, as one line linking the Ask issue (rule 3);
   - merged or done;
   - abandoned.

   For each, say what changed and what happens next. Started, progress, merge-main,
   conflict, re-gate and "still waiting on review" notes go in the bead or the PR's Status
   line, not in a comment.
3. **A decision for River is an Ask issue, never a comment.** When an item needs River to
   decide or act, file one RIV issue labelled `needs-river`, in Todo, assigned to River.
   It holds everything she needs to answer:
   - **Title:** `<item>: <decision> (<default> recommended)`.
   - **Decision:** one line.
   - **Options:** each with its trade-off; mark the recommended default.
   - **Context:** at most 10 lines, plus links. She shouldn't need to open anything else.
   - **If you pick X:** what happens next.
   - **Blocks:** the items and PRs waiting on it.

   The work item gets one line, `Blocked on RIV-nnn`, and nowhere else restates the ask.
   Polecats whose Linear key can't see RIV report "needs a decision" to their bead, and
   their dispatcher files the Ask issue within one sweep. An item deliberately not handled
   still says so on the item (never skip silently), with the reason and a link to the
   Ask issue if River has to act.
4. **Make Ask issues answerable in one line.** Offer the options, recommend a default, and
   give the exact reply that picks one, e.g. "`split it out` or `keep it`".
5. **Ownership is explicit.** The owner of an item owns its outcome until it's done or
   handed off on the item itself. Delegating the work doesn't hand off the outcome (see
   rule 8). A new session that takes over an item acknowledges again only if the owner
   changed.
6. **Close the loop with evidence.** When it's finished, say so where the ask was made,
   with a SHA, a link or the result. Then resolve the thread or issue if it's yours to
   resolve. When River answers an Ask issue, the agent that acts on the answer closes it
   and removes `needs-river` in the same step. `needs-river` is only ever on an open
   issue that is waiting on River.
7. **Communicate first, then act.** Announce first, then work. Report decisions and changes
   that need someone to act promptly, and don't batch them into a later summary.
8. **If you manage agents, you watch them.** This applies to anyone who hands out work: for
   example Gigi for polecats, phagey for the crews it sends work to, and the deacon for
   dogs.
   - **Know who's on what.** Keep a current map: agent → bead → item.
   - **Check that they're alive on a schedule,** not only when a turn finishes. A session
     that has crashed, is waiting at a prompt, or has gone quiet past its expected time
     counts as unavailable. Don't wait for the agent to report it; it can't.
   - **When an agent is unavailable:**
     - Save its work: push or bundle the branch.
     - Hand the work to another agent, or resume it yourself.
     - Post the change on the item only if the owner changes, e.g. "X stopped; Y is
       continuing from <branch/SHA>".
     - After repeated failures, escalate instead of retrying in a loop, and say so on the
       item.
   - **No news isn't progress.** Check, don't assume.
9. **Edit, don't repost.** When an Ask issue's context changes, edit its description and add
   one comment, `edited: <what changed>`, because Linear doesn't notify on edits. A
   correction never creates a new ask or a second copy of an old one.

Agents sign their posts using the conventions they already follow (e.g.
`~ Δ Delta, downstream of River`), so a reader can tell agent posts from River's own.
Where you can, name the agent in the signature (e.g. `~ gigi, Δ Delta, downstream of
River`), so River can tell which agent wrote it.
