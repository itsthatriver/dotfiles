# Phase 0-2: Context Check & Discovery

**Entry:** Agent detects feature-level work OR resumes ticket at `intake` phase.

---

## Context Check (Required)

Before any discovery rounds, verify goal and scope exist.

### Steps

1. **Read existing context** -- check for spec, ticket, or Linear issue description
2. **Check for goal AND scope sections**
3. **If missing or incomplete**, ask context questions:
   - "What is the goal? What should users/systems be able to do after this?"
   - "What is in scope? What are we building?"
   - "What is explicitly out of scope?"
4. **Create or update** the ticket/spec with answers

**Exit context check:** Goal AND scope are documented.

**Edge case:** User gives partial answer (goal but not scope). Ask only for missing field. Do not re-ask answered questions.

### IaC-Specific Context Questions

When the project involves infrastructure as code (OpenTofu, Pulumi, Crossplane):

| Question                              | Why It Matters                          |
|---------------------------------------|-----------------------------------------|
| What resources are created/managed?   | Defines the module boundary             |
| What provider(s) and versions?        | Constrains implementation options       |
| What are the input variables?         | Defines the public interface            |
| What outputs do consumers need?       | Defines the contract                    |
| What existing state might conflict?   | Prevents import/drift issues            |

---

## Discovery (Optional but Recommended)

After context check, offer discovery:

> "Want to explore edge cases before we define scenarios?"

**If user declines** (or says "ready"): update phase to `define-behavior`, proceed to SCENARIOS.md.

**If user accepts**: run discovery rounds.

### Discovery Rounds

Ask 2-3 targeted questions per round. Max 5 rounds -- after round 5, proceed automatically.

| Round | Theme                    | Example Questions                                                              |
|-------|--------------------------|--------------------------------------------------------------------------------|
| 1     | API contracts/interfaces | "What does the public API look like?" / "What inputs and outputs matter?"      |
| 2     | Failure modes            | "What breaks? What are the consequences?" / "What happens on timeout?"         |
| 3     | Boundaries               | "What is the minimum viable behavior?" / "What is the maximum scope?"          |
| 4     | Concrete scenarios       | "Walk me through a specific use case end-to-end"                               |
| 5     | Regret/edge cases        | "If we skip this, what support tickets come in?" / "What will we wish we had?" |

### Language-Specific Discovery Prompts

| Project Type | Round 1 (Contracts)                     | Round 2 (Failures)                        |
|--------------|-----------------------------------------|-------------------------------------------|
| **Go**       | "What interfaces does this implement?"  | "What errors should callers handle?"      |
| **Python**   | "What is the function signature?"       | "What exceptions can be raised?"          |
| **OpenTofu** | "What are the module inputs/outputs?"   | "What if the resource already exists?"    |
| **Pulumi**   | "What is the component resource API?"   | "What happens on partial deploy failure?" |
| **Shell**    | "What are the flags and arguments?"     | "What if a dependency is missing?"        |

### Round Flow

```
Agent: "Round 2 - Failure modes. What happens when the API returns a 429?"
User:  "We should retry with backoff. After 3 retries, fail with a clear error."
Agent: "Got it -- retry with backoff, hard fail after 3. Another round or ready?"
```

After each round: "Another round or ready to proceed?"

### Capture Insights

Record discovery findings:

- **Local**: Add `## Discovery` section to ticket.md with bullet points per round
- **Linear**: Add comment to parent issue with discovery notes

---

## Phase 0-2 Exit (Required)

Before proceeding to Phase 3 (define-behavior):

### Local Tracking

1. Verify ticket exists at `.project/tickets/{id}-{slug}/ticket.md`
2. Update frontmatter: `phase: define-behavior`
3. Add work log entry:
   ```
   - {timestamp} Complete: Phase 0-2 - Context established, {N} discovery rounds
   ```

### Linear Tracking

1. Update sub-issue `[BDD:Discovery]` status to Done
2. Add comment to parent issue: "Discovery complete. {N} rounds. Proceeding to scenario definition."
3. Create sub-issue `[BDD:Scenarios]` if not already present

---

## Decision Tree

```
START
  |
  v
Context exists (goal + scope documented)?
  YES --> Offer discovery rounds
  NO  --> Ask context questions first
            |
            v
          Context complete?
            YES --> Offer discovery rounds
            NO  --> Keep asking (only missing fields)
  |
  v
User wants discovery?
  YES --> Run rounds (max 5)
            |
            v
          After each round: "Another round or ready?"
            READY --> Exit to define-behavior
            CONTINUE --> Next round
            ROUND 5 --> Auto-exit to define-behavior
  NO  --> Exit to define-behavior
  |
  v
Update phase, log transition, proceed to SCENARIOS.md
```
