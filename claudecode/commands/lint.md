---
description: Run linters and formatters for the detected project type(s)
---

# Lint

Run the full linting and formatting suite. Detect project type(s) and run all applicable tools.

## Instructions

Run these commands based on detected project type. Multiple languages may apply in polyglot projects.

```bash
# Go (if go.mod exists)
[ -f go.mod ] && {
  golangci-lint run --fix ./... 2>&1 || true
}

# Python (if pyproject.toml or requirements.txt exists)
([ -f pyproject.toml ] || [ -f requirements.txt ]) && {
  ruff check --fix . 2>&1 || true
  ruff format . 2>&1 || true
}

# Terraform / OpenTofu (if .tf files exist)
ls *.tf > /dev/null 2>&1 && {
  tofu fmt -recursive 2>&1 || terraform fmt -recursive 2>&1 || true
  tflint --recursive 2>&1 || true
}

# Shell (find .sh files)
find . -name '*.sh' -not -path '*/vendor/*' -not -path '*/.terraform/*' | head -20 | while read f; do
  shellcheck "$f" 2>&1 || true
done

# Markdown
markdownlint-cli2 --fix "**/*.md" 2>&1 || true

# YAML
yamllint -d relaxed . 2>&1 || true
```

## Summary

After running, report:
1. Any errors that couldn't be auto-fixed
2. Type errors (if applicable)
3. Total issues found vs fixed
