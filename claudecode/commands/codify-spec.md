---
description: Generate executable tests from a reviewed spec
---

# Codify Spec

Convert a reviewed spec's behaviors into executable test cases. Each behavior becomes a test.
Tests should fail (RED) because the feature doesn't exist yet.

## When to Use

- After `/review-spec` marks a spec as `reviewed`
- When behaviors are stable and ready to become executable tests

## Instructions

### 1. Load the Spec

If the user provides a path, read it. Otherwise, find reviewed specs:

```bash
grep -rl 'status: reviewed' .project/specs/ 2>/dev/null
```

If the spec status is `draft`, warn:

> This spec hasn't been reviewed yet. Run `/review-spec` first to catch ambiguity before codifying.

Proceed only if the user confirms.

### 2. Detect Project Conventions

Identify the language and test framework:

```bash
# Detect language
[ -f go.mod ] && echo "go"
[ -f pyproject.toml ] && echo "python"
[ -f package.json ] && echo "node"
[ -f Cargo.toml ] && echo "rust"

# Find existing test patterns
find . -name '*_test.*' -o -name 'test_*' | head -10
```

Adapt test file naming and structure to match existing project conventions.

### 3. Map Behaviors to Tests

For each numbered behavior in the spec, create one test:

| Spec section | Test mapping |
|-------------|-------------|
| Behavior N | One test function named after the behavior |
| Constraint | Assertion within relevant behavior tests, or dedicated test if cross-cutting |
| Edge Case | One test function per edge case |

**Test naming convention** (must match guard hook patterns):

| Language | Pattern | Example |
|----------|---------|---------|
| Python | `test_spec_<slug>.py` | `test_spec_webhook_retry.py` |
| Go | `spec_<slug>_test.go` | `spec_webhook_retry_test.go` |
| JS/TS | `spec_<slug>_test.ts` | `spec_webhook_retry_test.ts` |

Or place tests in a `spec_tests/` directory if the project uses directory-based organization.

### 4. Write Tests

Each test should:

- Reference the behavior number in a comment (e.g., `# Behavior 3: retries use exponential backoff`)
- Test the observable outcome, not implementation details
- Use arrange/act/assert structure
- Fail meaningfully — the assertion message should describe expected behavior
- Import nothing that doesn't exist yet — use interfaces/stubs if needed

Write tests to the project's test directory.

### 5. Verify RED

```bash
# Run the spec tests — they should all fail
# Go
[ -f go.mod ] && go test -run 'Spec' -v ./... 2>&1 || true

# Python
[ -f pyproject.toml ] && pytest -k 'spec' -v 2>&1 || true
```

All tests should fail (feature not implemented) or fail to compile (dependencies not yet created).
If any test passes, it's testing the wrong thing — fix it.

### 6. Update Status

Update the spec frontmatter:

```yaml
---
status: codified
---
```

### 7. Report

```text
## Spec Codified

**Spec:** .project/specs/<slug>.md
**Status:** codified
**Test file:** <path to generated test file>
**Tests generated:** N (from N behaviors + N edge cases)
**All failing:** Yes (RED — ready for implementation)
**Next step:** /review-spec-tests for adversarial review, then implement
```
