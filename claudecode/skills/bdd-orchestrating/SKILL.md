---
name: bdd-orchestrating
description: Feature-level BDD workflow. Use when task requires 3+ files AND new state/flows, or user says 'feature', 'add', 'implement', 'build'. NOT for bug fixes, typos, config changes, or 1-2 file tasks. Defines behavior before implementation.
allowed-tools: '*'
---

# BDD Orchestrator

Behavior-first development for features. Discovery, then scenarios, then implementation.

**Iron Law:** DEFINE BEHAVIOR BEFORE IMPLEMENTATION.

---

## Work Level Detection

Run on EVERY request before doing work:

| Level     | Trigger                                | Action                              |
|-----------|----------------------------------------|-------------------------------------|
| **Patch** | Bug fix, typo, config change           | Fix directly                        |
| **Task**  | 1-2 files, one test, no new state      | TDD (RED, GREEN, REFACTOR)          |
| **Feature** | 3+ files AND new state/flows         | Full BDD flow (this skill)          |

Announce: "Patch. Fixing directly." / "Task. Writing tests first. `/bdd` to override." / "Feature. Defining behaviors first."

---

## Phase Tracking

Features progress through phases. Track state in the appropriate location:

### If Linear Issue Exists

1. Check for a linked Linear issue (user provides identifier or issue is referenced in context)
2. Create sub-issues for each BDD phase as work begins
3. Sync phase transitions as comments on the parent issue
4. Update sub-issue status as phases complete

### If No Linear Issue (Local Fallback)

Track in ticket frontmatter at `.project/tickets/{id}-{slug}/ticket.md`:

```yaml
---
type: feature
phase: implement  # intake | define-behavior | scenario-gate | decomposition | implement | done
---
```

### Phase Definitions

| Phase               | What Happens                              | Details          |
|---------------------|-------------------------------------------|------------------|
| `intake`            | Context check, discovery (rounds 0-5)     | DISCOVERY.md     |
| `define-behavior`   | Writing Given/When/Then scenarios          | SCENARIOS.md     |
| `scenario-gate`     | Validating scenarios (AOD quality gate)    | SCENARIOS.md     |
| `decomposition`     | Component breakdown + test layer assignment | DECOMPOSITION.md |
| `implement`         | Outside-in TDD per scenario               | TDD.md           |
| `done`              | Cleanup, verification, completion checks  | DONE.md          |

**Update phase when:**

- Completing a BDD phase: set next phase
- Handing off to TDD: set `implement`
- All scenarios pass: set `done`

---

## Artifact Levels

| Level     | Required Artifacts                         |
|-----------|--------------------------------------------|
| **Feature** | ticket.md + test-definitions.md (or Linear sub-issues) |
| **Task**    | ticket.md only (or Linear issue)          |
| **Patch**   | None (just fix and commit)                |

### Artifact-First Rule

Before doing work, create or verify the phase artifact:

| Phase         | Artifact (Local)                                                    | Artifact (Linear)                     |
|---------------|---------------------------------------------------------------------|---------------------------------------|
| intake        | `.project/tickets/{id}-{slug}/ticket.md`                           | Sub-issue: "Discovery: {feature}"     |
| define-behavior | `.project/tickets/{id}-{slug}/test-definitions.md`               | Sub-issue: "Scenarios: {feature}"     |
| decomposition | Task breakdown section in ticket.md                                 | Sub-issue: "Decomposition: {feature}" |
| implement     | Test files per scenario                                             | Sub-issue per component               |
| done          | Completion log                                                      | Parent issue comment with evidence    |

---

## Resume Logic

When user references a ticket or Linear issue, resume work:

1. **Read state** -- get current phase from ticket frontmatter or Linear sub-issue status
2. **Find progress** -- first unchecked `[ ]` in test-definitions or first incomplete scenario
3. **Check context** -- read last work log entry or most recent Linear comment
4. **Announce resume** -- "Resuming at [phase]. Last completed: [summary]."

### Resume by Phase

| Phase               | Resume Action                                    |
|---------------------|--------------------------------------------------|
| `intake`            | Start or continue context check / discovery      |
| `define-behavior`   | Continue drafting scenarios                      |
| `scenario-gate`     | Continue validating scenarios against AOD gate   |
| `decomposition`     | Continue task breakdown                          |
| `implement`         | Find first unchecked scenario, run TDD cycle     |
| `done`              | Run `/done` and `/audit` checks                  |

---

## Linear Integration

### When Linear Issue Exists

```
Decision tree:
  1. User provides Linear issue identifier?
     YES --> Read issue, check for existing sub-issues
             - Sub-issues exist? Resume at current phase
             - No sub-issues? Create them as work begins
     NO  --> Check if task description references Linear
             - Found? Use that issue
             - Not found? Use local fallback
```

**Sub-issue naming convention:**

- `[BDD:Discovery] {feature name}`
- `[BDD:Scenarios] {feature name}`
- `[BDD:Decomposition] {feature name}`
- `[BDD:Implement] {component name}`
- `[BDD:Done] {feature name}`

**Comment sync points:**

- Phase transition: "Phase transition: {old} -> {new}"
- Scenario defined: post scenario list as checklist
- Scenario implemented: check off in comment, link test evidence
- Completion: post summary with test results

### When No Linear Issue

Use local file tracking:

```
.project/
  tickets/
    {id}-{slug}/
      ticket.md           # Phase tracking + work log
      test-definitions.md  # BDD scenarios with checkboxes
```

---

## Phase Files

Load the appropriate file based on current phase:

| Phase               | File             |
|---------------------|------------------|
| `intake`            | DISCOVERY.md     |
| `define-behavior`   | SCENARIOS.md     |
| `scenario-gate`     | SCENARIOS.md     |
| `decomposition`     | DECOMPOSITION.md |
| `implement`         | TDD.md           |
| `done`              | DONE.md          |

---

## Splitting (Inline)

Splitting is **suggested, not mandatory** -- user decides.

| Checkpoint   | Trigger                               | Action                      |
|--------------|---------------------------------------|-----------------------------|
| **Entry**    | 2+ user stories OR vague scope        | Split into epic + features  |
| **Phase 3**  | >15 scenarios OR 3+ distinct clusters | Split by user journey       |
| **Phase 5**  | >20 tasks OR 5+ major components      | Split by component/layer    |

If user declines: log "Split suggested but user declined", continue at current phase, do not re-suggest at same checkpoint this session.

---

## Key Takeaways

- **Patch/Task**: TDD directly (RED, GREEN, REFACTOR)
- **Feature**: Full BDD flow (all phases), track in ticket or Linear
- **Resume**: Read state, find first unchecked scenario, continue
- **Done gate**: Run `/done` before marking complete
- When unsure: default to task, user can `/bdd` to override
