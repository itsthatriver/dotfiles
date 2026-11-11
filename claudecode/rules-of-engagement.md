# Rules of Engagement for Work Items

These apply to every agent, and every person, acting on River's work items: Linear issues
(RIV, PLT, TOO and the rest), pull requests and their review threads, beads, and mail.

## I Got It

It doesn't matter who does the work. What matters is that the outcome is understood and
owned. Whoever is responsible for an outcome drives it to completion, by doing the work or
by working with others, and communicates proactively so nobody has to ask for an update.

If someone looking at a ticket has to wonder "is anyone on this?" or "has the automation
broken?", we've failed, even if the work is going fine.

**Where agents differ from people:** an agent can stop, by crashing, getting stuck at a
prompt or hitting a context limit, without noticing and without telling anyone. So "it
doesn't matter who does the work" applies to doing the work, not to accountability.
Delegating work never delegates the outcome. The manager who handed it out stays
accountable until it's done.

## The rules

1. **Acknowledge where the ask was made, as soon as you pick it up.** Reply on the same
   issue, comment thread or PR thread. Say what will happen, who or which agent or bead is
   doing it, and what "done" looks like. Mail between agents doesn't count: River can't see
   it.
2. **Report each state change in the same place.** That covers started, blocked, waiting on
   a decision, ready for review, done or merged, and abandoned. For each, say what changed
   and what happens next.
3. **Never skip silently.** If an item is deliberately not handled, whether it's held for a
   decision, out of scope, or waiting on someone, say so on the item: give the reason and
   the call to action (who has to do what, and the exact reply that unblocks it). When
   River is the one who has to act, also file a RIV issue labelled `needs-river` that links
   to it.
4. **Make calls to action answerable in one line.** Offer the options, recommend a default,
   and give the exact reply that picks one, e.g. "`split it out` or `keep it`".
5. **Ownership is explicit, and accountability stays with the delegator.** Whoever picks an
   item up owns the outcome. If they delegate the work to a polecat, a crew agent or a dog,
   the delegate owns doing it, but the delegator still owns the outcome. State every
   handoff on the item. When a new session takes over, it acknowledges on the item again
   before carrying on.
6. **Close the loop with evidence.** When it's finished, say so where the ask was made,
   with a SHA, a link or the result. Then resolve the thread or issue if it's yours to
   resolve.
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
     - Post the change on the item, e.g. "X stopped; Y is continuing from <branch/SHA>".
     - After repeated failures, escalate instead of retrying in a loop, and say so on the
       item.
   - **No news isn't progress.** Check, don't assume.

Agents sign their posts using the conventions they already follow (e.g.
`~ Δ Delta, downstream of River`), so a reader can tell agent posts from River's own.
