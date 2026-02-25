---
description: Run comprehensive code audit for architecture, dead code, and quality
---

# Audit

Run a comprehensive code quality audit. Execute checks and report results by severity.

## Instructions

### 1. Code Quality Checks

```bash
# Go (if go.mod exists)
[ -f go.mod ] && {
  echo "=== Go: Vet ==="
  go vet ./... 2>&1 || true

  echo "=== Go: Lint ==="
  golangci-lint run ./... 2>&1 || true

  echo "=== Go: Outdated ==="
  go list -m -u all 2>&1 | grep '\[' || echo "All modules up to date"
}

# Python (if pyproject.toml or requirements.txt exists)
([ -f pyproject.toml ] || [ -f requirements.txt ]) && {
  echo "=== Python: Ruff ==="
  ruff check . 2>&1 || true

  echo "=== Python: Type Check ==="
  ty check 2>&1 || true
}

# Terraform / OpenTofu (if .tf files exist)
ls *.tf > /dev/null 2>&1 && {
  echo "=== Terraform: Validate ==="
  tofu validate 2>&1 || terraform validate 2>&1 || true

  echo "=== Terraform: TFLint ==="
  tflint --recursive 2>&1 || true
}

# Shell
echo "=== Shell: ShellCheck ==="
find . -name '*.sh' -not -path '*/vendor/*' -not -path '*/.terraform/*' | head -20 | while read f; do
  shellcheck "$f" 2>&1 || true
done
```

### 2. Agent Config Checks

Find and check all agent configuration files:

- `CLAUDE.md`, `AGENTS.md` (root and subdirectories)
- `.claude/settings.json`

**For each config file, check:**

| Check | Criteria | Severity |
|-------|----------|----------|
| Size | CLAUDE.md: ~150-200 instructions | warn |
| Dead refs | All referenced files/paths exist | error |
| Staleness | Last modified 30+ days ago AND commits since | warn |

### 3. Report Format

```text
=== Errors (must fix) ===
- [E001] Description

=== Warnings (should review) ===
- [W001] Description

=== Summary ===
Errors: N | Warnings: N | Passed: N
```
