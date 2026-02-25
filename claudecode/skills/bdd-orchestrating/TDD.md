# Phase 6: Implementation (TDD)

**Entry:** Agent enters `implement` phase (after decomposition complete).

**Iron Law:** NO IMPLEMENTATION UNTIL A TEST FAILS FOR THE RIGHT REASON.

Announce: "Entering implementation. TDD mode for each scenario."

---

## Outside-In Test Layering

Build from the outside in:

1. **E2E first** -- prove user-facing behavior works end-to-end
2. **Integration** -- test component boundaries with real dependencies
3. **Unit** -- test isolated logic, mock only when necessary

This ordering ensures you build what users need, not what feels technically convenient.

---

## Walking Skeleton (First Scenario Only)

If no test infrastructure exists for this project, build the thinnest possible skeleton first:

| Project Type | Walking Skeleton                                              |
|--------------|---------------------------------------------------------------|
| **Go**       | `main.go` + handler that returns 200 + `_test.go` that calls it |
| **Python**   | `__init__.py` + function + `test_` file with one assertion     |
| **OpenTofu** | `main.tf` + `variables.tf` + `outputs.tf` + `tests/basic.tftest.hcl` |
| **Pulumi**   | `__main__.py` or `main.go` + one resource + test file          |
| **Shell**    | Script with `--help` flag + bats test that checks exit code   |

The skeleton proves: input arrives, processing happens, output appears. No real logic yet.

---

## Detect Project Test Runner

Before writing tests, detect what the project uses. Do not assume a framework.

### Detection Order

1. Check existing test files for import patterns
2. Check config files for test runner configuration
3. Check dependency files for test libraries
4. Fall back to language defaults

### Detection Matrix

| Language   | Config Files to Check                           | Default Runner         |
|------------|--------------------------------------------------|------------------------|
| **Go**     | `go.mod` (testify, gomega)                      | `go test ./...`        |
| **Python** | `pyproject.toml` [tool.pytest], `setup.cfg`, `tox.ini` | `pytest`         |
| **OpenTofu** | `*.tftest.hcl` files                          | `tofu test`            |
| **Pulumi** | `go.mod`, `pyproject.toml`, `package.json`       | Language test runner    |
| **Shell**  | `test/` dir with `.bats` files                   | `bats`                 |

### Run Commands

| Runner            | Run All                  | Run Single File                     | Run Single Test               |
|-------------------|--------------------------|--------------------------------------|-------------------------------|
| `go test`         | `go test ./...`          | `go test ./pkg/auth/`               | `go test ./pkg/auth/ -run TestLogin` |
| `pytest`          | `pytest`                 | `pytest tests/test_auth.py`         | `pytest tests/test_auth.py::test_login` |
| `tofu test`       | `tofu test`              | `tofu test -filter=tests/basic.tftest.hcl` | N/A (run file)          |
| `pulumi` (Go)     | `go test ./...`          | `go test ./tests/`                  | `go test ./tests/ -run TestVpc` |
| `pulumi` (Python) | `pytest`                 | `pytest tests/test_infra.py`        | `pytest tests/test_infra.py::test_vpc` |
| `bats`            | `bats test/`             | `bats test/cli.bats`               | `bats test/cli.bats -f "shows usage"` |

---

## For Each Scenario: RED, GREEN, REFACTOR

### 6.1 RED -- Write Failing Test

1. Pick ONE test from test-definitions (first unchecked `[ ]`)
2. Write test code that translates the Given/When/Then into assertions
3. Run test -- verify it fails for the RIGHT reason

**Right reason:** The behavior is missing (function not found, endpoint returns 404, resource not in plan).
**Wrong reason:** Syntax error, import missing, test framework misconfigured.

4. Commit: `test: {scenario name}`

#### Red Flags -- STOP Immediately

| Flag                        | Problem                    | Action                              |
|-----------------------------|----------------------------|--------------------------------------|
| Test passes immediately     | Testing nothing useful     | Rewrite the assertion to be meaningful |
| Syntax/compile error        | Test code is broken        | Fix the test code, not the production code |
| Wrote implementation first  | Skipped RED phase          | Delete implementation, return to test |
| Multiple tests at once      | Not atomic                 | Pick ONE scenario, delete the rest   |
| Test depends on another test | Not isolated              | Each test must set up its own state  |

### 6.2 GREEN -- Minimal Implementation

**Iron Law:** ONLY WRITE CODE THE FAILING TEST REQUIRES.

1. Write the minimal code to make the failing test pass
2. Run the single test -- verify it passes
3. Run the FULL test suite -- verify no regressions
4. Commit: `feat: {scenario name}`

**Evidence before claims:** Show test output. Do not just claim "tests pass" -- run them and display the results.

#### Minimal Implementation Guidelines

| Temptation                    | Instead Do This                        |
|-------------------------------|----------------------------------------|
| Add error handling for cases not yet tested | Return the happy path only   |
| Refactor while implementing   | Get to GREEN first, refactor after     |
| Generalize the solution       | Hardcode if only one test needs it     |
| Add logging, metrics, tracing | Not until a test requires it           |

### 6.3 REFACTOR -- Clean Up

After GREEN, run `/refactor` for cleanup. It handles:

- Duplication extraction
- Name clarity
- Function length
- Magic values
- Dead code removal

**Rules for refactoring phase:**

- Tests must stay GREEN throughout. If a refactor breaks tests, revert.
- One refactoring at a time. Test after each change.
- Commit after each successful refactor: `refactor: {what improved}`

### 6.4 Mark & Iterate

Before marking a scenario complete:

1. **Confirm refactor status** (say one of these):
   - "Refactored: {what improved}" + show refactor commit
   - "No refactoring needed: code is clean"
2. Mark scenario `[x]` in test-definitions.md
3. If using Linear: update scenario checklist, add comment with test evidence
4. Return to 6.1 for next unchecked scenario
5. All scenarios done? Proceed to Phase 7 (DONE.md)

---

## Commit Convention Summary

| Phase      | Prefix                  | Example                                    |
|------------|-------------------------|--------------------------------------------|
| RED        | `test:`                 | `test: valid request returns user profile` |
| GREEN      | `feat:`                 | `feat: valid request returns user profile` |
| REFACTOR   | `refactor:`             | `refactor: extract user lookup to helper`  |
| Walking skeleton | `chore:`          | `chore: add test infrastructure`           |

---

## IaC-Specific TDD Notes

### OpenTofu TDD Cycle

```
RED:    Write .tftest.hcl with expected plan output assertions
        Run `tofu test` -- fails (resource not defined yet)
GREEN:  Add resource to .tf file with minimum attributes
        Run `tofu test` -- passes
REFACTOR: Clean up variable names, add descriptions, organize files
        Run `tofu test` -- still passes
```

### Pulumi TDD Cycle

```
RED:    Write unit test asserting resource properties via mock monitor
        Run `go test` or `pytest` -- fails (component not defined)
GREEN:  Implement component resource with minimum properties
        Run test -- passes
REFACTOR: Extract reusable patterns, clean up resource naming
        Run test -- still passes
```

### IaC Test Assertions

| What to Assert               | How                                           |
|------------------------------|-----------------------------------------------|
| Resource exists in plan      | Count resources of type in plan output         |
| Resource has correct attributes | Check specific attribute values in plan      |
| No unexpected changes        | Assert plan has exactly N changes              |
| Output values correct        | Check module/stack outputs after apply         |
| Resources actually created   | Query cloud API after apply (integration/E2E)  |

---

## Troubleshooting

| Problem                              | Likely Cause                          | Fix                                   |
|--------------------------------------|---------------------------------------|---------------------------------------|
| Test passes but behavior is wrong    | Assertion is too loose                | Tighten the assertion                 |
| Test fails after refactor            | Refactor changed behavior             | Revert refactor, try smaller change   |
| Cannot write a test for this         | Component has too many responsibilities | Extract the testable part first      |
| Test is flaky (sometimes passes)     | Non-deterministic dependency          | Mock time, randomness, external state |
| Full suite is slow                   | Too many integration/E2E tests        | Push logic down to unit tests         |
