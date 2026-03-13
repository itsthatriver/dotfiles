---
description: Stress-test a spec for ambiguity, missing edge cases, and unclear behaviors
---

# Review Spec

Adversarial review of a spec artifact. Surface problems before they become implementation bugs.

## When to Use

- After `/build-spec` creates a draft spec
- When revisiting a spec before codifying
- When someone questions whether a spec is complete

## Instructions

### 1. Load the Spec

If the user provides a path, read it. Otherwise, list specs:

```bash
ls .project/specs/*.md 2>/dev/null
```

If multiple exist, ask which one to review. If one exists, use it.

### 2. Analyze Each Section

For each section, apply these lenses:

| Section | Review lens |
|---------|-------------|
| Intent | Is the "why" clear? Could two engineers disagree on the goal? |
| Behaviors | Is each statement observable and testable? Any implicit assumptions? |
| Constraints | Are these actually invariants, or just nice-to-haves? Any missing performance/security constraints? |
| Edge Cases | What inputs break the happy path? What happens at boundaries (zero, one, max, empty, concurrent)? |
| Non-Goals | Does the scope fence have gaps? Could someone argue a missing behavior is "in scope"? |

### 3. Apply Stress Tests

Run these checks against the behaviors:

1. **Ambiguity test:** Can any behavior be interpreted two different ways?
2. **Completeness test:** What happens when each behavior's precondition is NOT met?
3. **Conflict test:** Do any behaviors contradict each other?
4. **Boundary test:** What happens at zero, one, max, empty, null, concurrent?
5. **Failure test:** What happens when external dependencies fail?
6. **Security test:** Can any behavior be exploited or abused?

### 4. Report Findings

Present findings grouped by severity:

```text
## Spec Review: <name>

### Must Fix
- [B3] "User receives confirmation" — confirmation how? Email? UI toast? Both?
- ...

### Should Consider
- No behavior covers concurrent access — what if two users edit simultaneously?
- ...

### Looks Good
- Intent is clear and focused
- Non-goals fence is well-defined
- ...
```

### 5. Iterate

Work with the user to resolve findings. Update the spec in place.

### 6. Update Status

Once the user approves the reviewed spec, update the frontmatter:

```yaml
---
status: reviewed
---
```

```text
## Spec Reviewed

**File:** .project/specs/<slug>.md
**Status:** reviewed
**Findings resolved:** N
**Next step:** /codify-spec to generate executable tests
```
