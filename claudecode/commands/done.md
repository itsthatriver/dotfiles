---
description: Run completion checklist for current feature or task
---

# Done

Run the completion checklist before marking work complete.

## Instructions

### 1. Run Automated Checks

Run `/lint` first to auto-fix style issues, then:

```bash
# Go
[ -f go.mod ] && go test ./... 2>&1 && go build ./... 2>&1

# Python
([ -f pyproject.toml ] || [ -f requirements.txt ]) && pytest 2>&1

# Terraform
ls *.tf > /dev/null 2>&1 && {
  tofu validate 2>&1 || terraform validate 2>&1
  tofu test 2>&1 || true
}
```

### 2. Flake Detection

Run tests 3x to detect flaky tests:

```bash
# Go
go test -count=3 ./...

# Python
pytest --count=3

# Terraform
tofu test && tofu test && tofu test
```

### 3. Validate Scenarios (if BDD)

If test-definitions.md exists:
1. Count total scenarios: `- [` lines
2. Count completed: `- [x]` lines
3. Report: "Scenarios: X/Y complete"

### 4. Linear Integration

If work is linked to a Linear issue:
- Update issue status
- Post completion comment with test evidence
- Close BDD sub-issues

### 5. Report

```text
## Done Checklist

**Tests:** ✓ N/N pass (or ✗ N failures)
**Build:** ✓ Success (or ✗ Failed)
**Lint:** ✓ Clean (or ✗ N errors)
**Scenarios:** All N complete (or ✗ X/Y)

[Ready to mark done / Fix these first: ...]
```
