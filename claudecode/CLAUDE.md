# Global Instructions — Individual Layer

This file is the **individual layer** of a 3-tier instruction system (individual -> org -> repo).
It encodes personal development process and philosophy. Org and repo layers may override specifics.

---

## Work Level Detection

**Announce the level at the start of EVERY response that involves code changes.**

| Level | Trigger | Workflow |
|---------|-----------------------------------------------|-------------------------------------------|
| Patch | Bug fix, typo, config change | Fix directly, test, commit |
| Task | 1-2 files, one test, no new state | TDD: RED -> GREEN -> REFACTOR |
| Feature | 3+ files AND new state/flows | BDD: define behavior before implementation |

**Decision tree — stop at first match:**

1. Bug fix, typo, or config change? -> **Patch**
2. Mentions "feature", "add", "implement", "support", or "build" AND touches 3+ files AND introduces new state or flows? -> **Feature**
3. Can ONE test cover the observable change? -> **Task**
4. Fallback -> **Task**

---

## Code Philosophy

Optimize for **Clarity -> Simplicity -> Correctness**, in that order. Clear code that is simple to follow will trend toward correctness. Clever code does the opposite.

| Principle | Meaning |
|-------------------|-------------------------------------------------------------------------|
| Elegant code | Reads like prose. Intent is obvious without comments explaining "why". |
| No bloat | Every file, function, and dependency must justify its existence. |
| Explicit errors | Fail loudly with context. Never swallow exceptions silently. |
| Self-documenting | Names, types, and structure convey behavior. Comments explain "why", not "what". |

**Tie-breaker rule:** When two approaches are equivalent in correctness, pick the one a junior engineer would understand on first read.

---

## Anti-Patterns

| Don't | Do | Why |
|---------------------------------------|--------------------------------------------------|----------------------------------------------|
| `catch(e) {}` | `catch(e) { log(e); throw }` or handle explicitly | Silent failures hide bugs for days |
| Utility class for one function | Export the function directly | A class with one static method is just a namespace tax |
| Factory/builder for a simple object | Use a constructor or literal | Indirection without payoff |
| `data`, `tmp`, `val`, `x` as names | Name describes content or purpose | Future-you is a stranger |
| Code "for later" / speculative hooks | Delete it; git remembers | Dead code rots and misleads |
| >50 lines for a nice-to-have | Cut scope or open an issue | Gold-plating derails the actual task |

---

## Architectural Preferences

- **Interfaces and contracts first** — present options in terms of boundaries and abstractions, not implementations.
- **Standardized, reusable patterns** over one-off solutions.
- **Explain trade-offs** in terms of team scalability and maintenance burden.
- **Fewer tools with broader coverage** over many specialized tools.
- **Design for automation and self-service**, not tribal knowledge.
- **Composition over inheritance.**
- **Design data structures and interfaces before implementation.**
- Litmus test: *"If someone with no context inherits this in 6 months, can they operate it?"*

---

## Library and API Verification

Before using any library or API:

1. Check the **installed version** (`pip show`, `npm ls`, `go list -m`, etc.).
2. Look up the docs for **that version** — APIs change between releases.
3. If uncertain about an API's behavior or signature, **ask before guessing**.

Do not hallucinate function signatures. A wrong import is worse than asking a question.

---

## Existing Tooling Check

Before starting work on new tooling, automation, linting, or developer experience improvements,
search for existing solutions. Scale effort to the size of the task:

| Task size | Check |
|-----------|-------|
| Patch/small | `gh pr list --search '<keywords>'` + grep the repo for existing configs/scripts |
| Task | Above + search Linear for related issues (`Linear_ListIssues`) |
| Feature | Above + search Slack for prior discussions (`slack_search_public`) + check Google Docs if relevant |

Do not build what already exists or is already in-flight.

---

## Self-Testing

Never ask the user to test something you can test yourself. Run the tests. Read the output. Fix failures.

### Infrastructure-as-Code Testing Strategy

| Layer | Tools | When |
|-------------|------------------------------------------------------------------|----------------------------------------------|
| Static | `tofu validate`, `tflint`, `pulumi preview`, `crossplane render` | Always — run on every change |
| Unit | `tofu test` (mock providers, plan mode), Pulumi unit tests (mock monitor) | When testable logic exists |
| Integration | `tofu test` (apply mode), Pulumi Automation API | When repo provides test harness |
| Cloud/E2E | Leave to repo-level config | Only if test harness explicitly detected |

Run static checks automatically. Escalate through layers only when the repo supports it.

---

## Commit Discipline

- Commit after each **GREEN** phase, before and after refactoring, and when switching tasks.
- Commit messages must be descriptive enough for a new agent to reconstruct context from `git log` alone.
- **LOC gate:** commit before exceeding 400 lines of uncommitted changes.
- Small, atomic commits enable agent handoffs — the commit log IS the context transfer mechanism.
- Never bundle unrelated changes in one commit.

---

## PR Scope Discipline

Monitor PR growth continuously. When **any** threshold is crossed, stop current work and re-evaluate:

| Metric | Threshold |
|--------|-----------|
| Commits on branch | 5 |
| Lines changed (adds + dels) | 1000 |
| Files changed | 15 |
| Review fix-up rounds | 2 |

**When triggered:**

1. STOP. Announce: "PR scope check — [metric] at [value]/[threshold]."
2. Summarize what the PR currently contains (group by logical concern).
3. Propose 2-3 ways to break it down (stacked PRs, ship-what's-done + follow-up, extract standalone changes).
4. Wait for user direction before continuing.

A hook injects PR metrics into context automatically. If you see the warning and the user
continues without acting on it, respect that decision — the hook will suppress for several
prompts and only re-check if scope has grown further. The LOC gate (400 lines per commit)
catches local bloat; this catches PR-level bloat.

---

## Debugging

Use the `/debug` skill when available. Core rules regardless:

1. **Investigate root cause before ANY fix.** Read the error. Read the stack trace. Reproduce it.
2. One change at a time. Test after each change. Commit if green.
3. After **2-3 failed fix attempts**: STOP. Reassess the hypothesis. Ask the user.
4. Never shotgun-debug by changing multiple things simultaneously.

---

## Refactoring

Use the `/refactor` skill when available. Core rules regardless:

1. Refactoring means **changing structure without changing behavior**.
2. Tests must pass before AND after. If no tests exist, write them first.
3. One refactoring move at a time. Test. Commit.
4. After **2-3 failed attempts**: STOP. Reassess. Ask the user.

---

## BDD Workflow (Feature level only)

Use the `/bdd` skill when available. Iron law: **DEFINE BEHAVIOR BEFORE IMPLEMENTATION.**

### Phases

```text
intake -> define-behavior -> scenario-gate -> decomposition -> implement -> done
```

1. **Intake**: Clarify scope, identify actors, confirm acceptance criteria.
2. **Define Behavior**: Write Gherkin scenarios covering happy path, edge cases, and error paths.
3. **Scenario Gate**: User approves scenarios before any code is written.
4. **Decomposition**: Break approved scenarios into ordered implementation tasks.
5. **Implement**: TDD each task (RED -> GREEN -> REFACTOR). Commit after each GREEN.
6. **Done**: All scenarios pass. Clean up, final commit.

---

## Linear Integration

When work is associated with a Linear issue:

- Create **sub-issues** for BDD phases (define-behavior, implement, etc.).
- Post **phase transitions** and scenario completion as comments on the parent issue.
- Local project files remain the source of truth for agent context.

When no Linear issue exists: use local project files (`TODO.md`, feature specs) for tracking.

---

## Code Fence Languages

When writing markdown, **always specify the language** in fenced code blocks:

````markdown
```python
def example():
    pass
```
````

Never use bare triple-backtick fences. This enables syntax highlighting and tooling integration.
