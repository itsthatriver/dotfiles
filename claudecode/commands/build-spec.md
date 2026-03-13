---
description: Interactive interview that outputs a clean spec artifact
---

# Build Spec

Interview the user to capture behavioral intent for a feature, then output a spec artifact.
This is the primary entry point for spec-driven development — specs are interviewed, not hand-written.

## When to Use

- Starting a new feature and want to define behavior before implementation
- Capturing requirements from a conversation into a structured spec
- Before `/review-spec` — this creates the initial draft

## Instructions

### 1. Gather Context

If the conversation already contains feature context, summarize your understanding and confirm.
Otherwise, ask these questions (skip any already answered):

1. **What problem does this solve?** (becomes Intent)
2. **What should users/callers be able to do?** (becomes Behaviors)
3. **What must always be true?** (becomes Constraints)
4. **What inputs or states are unusual?** (becomes Edge Cases)
5. **What is explicitly out of scope?** (becomes Non-Goals)

Ask follow-up questions until each section has substance. Do not accept vague answers —
push for observable, testable statements.

### 2. Draft the Spec

Write the spec following the format in `claudecode/spec-format.md`:

```markdown
---
status: draft
---

# <Feature Name>

## Intent
...

## Behaviors
1. When X happens, the system does Y.
...

## Constraints
...

## Edge Cases
...

## Non-Goals
...
```

**Behavior statements must be:**
- Observable from the outside (not implementation details)
- Testable — each becomes an executable test via `/codify-spec`
- Numbered — order implies nothing, but numbers enable reference

### 3. Review with User

Present the full draft. Ask:

> Does this capture the feature? Anything missing, wrong, or out of scope?

Iterate until the user approves.

### 4. Write the Artifact

```bash
mkdir -p .project/specs
```

Write the approved spec to `.project/specs/<slug>.md` where `<slug>` is a kebab-case
name derived from the feature name (e.g., `webhook-retry-policy`).

### 5. Report

```text
## Spec Created

**File:** .project/specs/<slug>.md
**Status:** draft
**Behaviors:** N defined
**Next step:** /review-spec to stress-test before codifying
```
