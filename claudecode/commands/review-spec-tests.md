---
description: Adversarial review of spec tests — poke holes and force coverage
---

# Review Spec Tests

Adversarial review of a spec's generated tests. Goal: ensure the tests actually prove the
spec's behaviors and can't pass vacuously.

## When to Use

- After `/codify-spec` generates tests
- Before starting implementation
- When questioning whether tests are rigorous enough

## Instructions

### 1. Load Spec and Tests

Read both the spec and its generated test file:

```bash
# Find codified specs
grep -rl 'status: codified' .project/specs/ 2>/dev/null

# Find spec test files
find . -name 'test_spec_*' -o -name 'spec_*_test.*' -o -path '*/spec_tests/*' 2>/dev/null | grep -v __pycache__
```

If spec status is not `codified`, warn:

> This spec hasn't been codified yet. Run `/codify-spec` first.

### 2. Coverage Audit

Check every spec element has a corresponding test:

```text
## Coverage Matrix

| Spec element | Test | Status |
|-------------|------|--------|
| Behavior 1: ... | test_... | Covered / Missing / Weak |
| Behavior 2: ... | test_... | Covered / Missing / Weak |
| Constraint: ... | assertion in test_... | Covered / Missing / Weak |
| Edge case: ... | test_... | Covered / Missing / Weak |
```

Flag any gaps.

### 3. Apply Adversarial Checks

For each test, ask:

1. **Vacuous pass:** Could this test pass even if the feature is broken? (e.g., testing a mock instead of real behavior)
2. **Wrong granularity:** Does this test one behavior, or is it a kitchen-sink integration test?
3. **Assertion strength:** Are assertions specific enough? (`assert result` vs `assert result.status == 200`)
4. **Missing negative case:** Does it verify the behavior does NOT happen when preconditions aren't met?
5. **Determinism:** Could this test flake due to timing, ordering, or external state?
6. **Readability:** Can someone unfamiliar with the codebase understand what's being tested?

### 4. Report Findings

```text
## Spec Test Review: <name>

### Coverage: N/M behaviors covered

### Must Fix
- test_retry_on_failure: asserts retry was called but doesn't verify backoff timing (Behavior 2)
- Missing: no test for Constraint "concurrent retries not allowed"

### Should Strengthen
- test_delivery_logging: only checks log exists, not content (Behavior 5)

### Looks Good
- test_max_retries: correctly verifies 5-attempt limit with explicit count
- Edge case coverage is thorough
```

### 5. Fix Tests

Work with the user to address findings. Update tests directly — this review IS
the authorized modification path for spec tests (the guard hook will prompt, which is expected).

### 6. Update Status

Once the user approves:

```yaml
---
status: validated
---
```

### 7. Report

```text
## Spec Tests Validated

**Spec:** .project/specs/<slug>.md
**Status:** validated
**Tests:** <path to test file>
**Coverage:** N/M behaviors, N/N constraints, N/N edge cases
**Ready for implementation:** Yes — tests define the acceptance criteria
```
