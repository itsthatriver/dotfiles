# Phase 7: Done Gate

**Entry:** All scenarios marked `[x]` in test-definitions.md.

---

## Required Checks

Run `/done` to automate, or verify manually:

- [ ] All scenarios `[x]` in test-definitions.md
- [ ] Full test suite passes
- [ ] Build/compile succeeds (if applicable)
- [ ] Lint passes (`/lint`)
- [ ] No bypass patterns introduced without approval
- [ ] Audit clean (`/audit`) -- no errors (warnings OK)

### Check Commands by Language

| Language     | Tests Pass               | Build Succeeds              | Lint Clean                        |
|--------------|--------------------------|-----------------------------|-----------------------------------|
| **Go**       | `go test ./...`          | `go build ./...`            | `golangci-lint run`               |
| **Python**   | `pytest`                 | N/A (or `python -m py_compile`) | `ruff check . && ruff format --check .` |
| **OpenTofu** | `tofu test`              | `tofu validate`             | `tofu fmt -check -recursive && tflint` |
| **Pulumi**   | Language test runner      | `pulumi preview`            | Language linter                    |
| **Shell**    | `bats test/`             | `bash -n script.sh`         | `shellcheck script.sh`            |

---

## Flake Detection

Run the full test suite multiple times to catch flaky tests:

### By Language

| Language     | Flake Detection Command                                        |
|--------------|----------------------------------------------------------------|
| **Go**       | `go test -count=3 ./...`                                      |
| **Python**   | `for i in 1 2 3; do pytest || echo "FLAKE on run $i"; done`   |
| **OpenTofu** | `for i in 1 2 3; do tofu test || echo "FLAKE on run $i"; done` |
| **Shell**    | `for i in 1 2 3; do bats test/ || echo "FLAKE on run $i"; done` |

If any run fails when others pass, investigate before marking done:

1. Identify the flaky test
2. Check for non-deterministic inputs (time, randomness, external state)
3. Fix the root cause -- do not just retry
4. Re-run flake detection after fix

---

## Cross-Scenario Refactoring

After all scenarios pass, look for cleanup opportunities across the full implementation:

| Pattern to Find                    | Refactoring                              |
|------------------------------------|------------------------------------------|
| Duplicate setup code across tests  | Extract shared fixture or test helper    |
| Similar assertions repeated        | Create custom assertion helper           |
| Repeated mock/stub patterns        | Create mock factory or shared test double |
| Copy-pasted logic in production    | Extract shared module or function        |
| Similar error handling in multiple places | Create error wrapper or middleware  |

Run `/refactor` if clear wins exist. Do not gold-plate -- only refactor what demonstrably improves clarity or reduces duplication.

If refactoring is done, re-run the full test suite and flake detection.

---

## Tracking Completion

### If Linear Issue Exists

1. Update parent issue status to Done (or appropriate completion state)
2. Add completion comment to parent issue with evidence:

```markdown
## Feature Complete: {feature name}

### Test Results
- Unit: {N} passing
- Integration: {M} passing
- E2E: {K} passing
- Flake detection: 3/3 runs clean

### Scenarios Completed
- [x] Scenario 1: {name}
- [x] Scenario 2: {name}
- [x] Scenario 3: {name}

### Files Modified
- {list of files}

### Final Commit
`feat(scope): {summary}` -- {commit hash}
```

3. Close all BDD sub-issues that are still open:
   - `[BDD:Discovery]` -- Done
   - `[BDD:Scenarios]` -- Done
   - `[BDD:Decomposition]` -- Done
   - `[BDD:Implement]` sub-issues -- Done
   - `[BDD:Done]` -- Done

### If Local Tracking

1. Update ticket.md frontmatter:
   ```yaml
   phase: done
   status: done
   ```
2. Add work log entry:
   ```
   - {timestamp} Complete: Phase 7 - All {N} scenarios passing, lint clean, audit clean
   ```
3. Consider moving ticket to `.project/tickets/completed/`

---

## Parent Epic (If Applicable)

If the completed ticket has a parent (epic or Linear parent issue):

1. Add completion entry to parent's work log or add comment to parent Linear issue
2. Check if ALL children are done
3. If all children done: update parent status to Done

---

## Final Commit

After all checks pass:

1. Stage any remaining changes (ticket status updates, log entries)
2. Commit with feature scope:

```
feat(scope): {summary of the feature}

Scenarios:
- {scenario 1 name}
- {scenario 2 name}
- {scenario 3 name}

Test evidence: {N} unit, {M} integration, {K} E2E -- all passing
```

### Commit Scope Convention

| Project Type | Scope Examples                                    |
|--------------|---------------------------------------------------|
| **Go**       | `feat(auth):`, `feat(api):`, `feat(store):`       |
| **Python**   | `feat(pipeline):`, `feat(cli):`, `feat(models):`  |
| **OpenTofu** | `feat(vpc):`, `feat(s3):`, `feat(iam):`           |
| **Pulumi**   | `feat(network):`, `feat(compute):`, `feat(dns):`  |
| **Shell**    | `feat(setup):`, `feat(deploy):`, `feat(backup):`  |

---

## Done Checklist Summary

```
[ ] Scenarios:     All [x] in test-definitions.md
[ ] Tests:         Full suite passes
[ ] Build:         Compiles / validates
[ ] Lint:          /lint clean
[ ] Audit:         /audit no errors
[ ] Flakes:        3x test run clean
[ ] Refactor:      Cross-scenario cleanup done (or skipped with reason)
[ ] Tracking:      Linear updated OR ticket.md status set to done
[ ] Parent:        Epic/parent updated if applicable
[ ] Commit:        feat(scope): {summary}
```

When all boxes are checked, the feature is done. Move on.
