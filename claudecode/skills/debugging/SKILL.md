---
name: debugging
description: Systematic debugging with root cause investigation. Use when encountering bugs, errors, test failures, unexpected behavior, or when previous fix attempts failed. Enforces investigation before fixes. NOT for adding features or refactoring.
allowed-tools: '*'
---

# Systematic Debugger

Find root cause before fixing. Symptom fixes are failure.

**Iron Law:** NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST

## When to Use

Answer IN ORDER. Stop at first match:

1. Bug, error, or test failure? --> Use this skill
2. Unexpected behavior? --> Use this skill
3. Previous fix didn't work? --> Use this skill (especially important)
4. Performance problem? --> Use this skill
5. None of above? --> Skip this skill

**Use especially when:**

- Under time pressure (emergencies make guessing tempting)
- "Quick fix" seems obvious (red flag)
- Already tried 1+ fixes that didn't work

## The Four Phases

Complete each phase before proceeding.

### Phase 1: Root Cause Investigation

**BEFORE attempting ANY fix:**

#### 1. Read Error Messages Completely

```text
Don't skip past errors. They often contain the exact solution.
- Full stack trace (note line numbers, file paths)
- Error codes and messages
- Warnings that preceded the error
- For IaC: resource identifiers, provider errors, state drift messages
```

#### 2. Reproduce Consistently

| Can reproduce?  | Action                                               |
| --------------- | ---------------------------------------------------- |
| Yes, every time | Proceed to step 3                                    |
| Sometimes       | Gather more data -- when does it happen vs not?      |
| Never           | Cannot debug what you cannot reproduce -- gather logs |

#### 3. Check Recent Changes

```bash
git diff HEAD~5       # Recent code changes
git log --oneline -10 # Recent commits
```

What changed that could cause this? Dependencies? Config? Environment?

#### 4. Trace Data Flow (Root Cause Tracing)

When the error is deep in a call stack:

```text
Symptom: Error at line 50 in handler.go
    ^ Called by service.go:120
    ^ Called by router.go:45
    ^ Called by main.go:10  <-- ROOT CAUSE: bad input here
```

**Technique:**

1. Find where the error occurs (symptom)
2. Ask: "What called this with bad data?"
3. Trace up until you find the SOURCE
4. Fix at source, not at symptom

For IaC (Terraform/Pulumi): trace from the failing resource back through its dependencies, variable references, and data sources to find where the bad value originates.

#### 5. Multi-Component Systems

When a system has multiple layers (API, service, database, infrastructure):

```text
# Log at EACH boundary before proposing fixes
=== Layer 1 (API): request received ===
=== Layer 2 (Service): input processed ===
=== Layer 3 (DB): query executed ===
=== Layer 4 (Infra): resource provisioned ===
```

Run once to find WHERE it breaks. Then investigate that layer.

### Phase 2: Pattern Analysis

#### 1. Find Working Examples

Locate similar working code in the same codebase. What works that is similar?

#### 2. Identify Differences

| Working code         | Broken code         | Could this matter? |
| -------------------- | ------------------- | ------------------ |
| Handles nil/None     | No nil/None check   | Yes -- panic/crash |
| Uses context timeout | No timeout          | Yes -- hangs       |
| Validates input      | No validation       | Yes -- bad data    |
| Explicit state mgmt  | Implicit state      | Yes -- drift       |

List ALL differences. Don't assume "that can't matter."

#### 3. Check Other Environments

Does this issue exist in:
- Different OS / architecture?
- Different cloud region or account?
- Different dependency versions?
- CI vs local?

### Phase 3: Hypothesis Testing

#### 1. Form Single Hypothesis

Write it down: "I think X is the root cause because Y"

Be specific:

- BAD: "Something's wrong with the database"
- GOOD: "Connection pool exhausted because connections aren't released in the error path"

#### 2. Test Minimally

| Rule                     | Why                    |
| ------------------------ | ---------------------- |
| ONE change at a time     | Isolate what works     |
| Smallest possible change | Avoid side effects     |
| Don't bundle fixes       | Can't tell what helped |

#### 3. Log Each Attempt

```text
Attempt 1: Changed X because Y --> Result: still failing, but error changed to Z
Attempt 2: Changed A because B --> Result: fixed
```

#### 4. Evaluate Result

| Result          | Action                                  |
| --------------- | --------------------------------------- |
| Fixed           | Phase 4 (verify)                        |
| Not fixed       | NEW hypothesis (return to 3.1)          |
| Partially fixed | Found one issue, continue investigating |

### Phase 4: Implementation

#### 1. Create Failing Test

Before fixing, write a test that fails due to the bug:

**Go:**
```go
func TestHandlesEmptyInput(t *testing.T) {
    // This test should FAIL before fix, PASS after
    result, err := ProcessData("")
    if err != nil {
        t.Fatalf("expected no error for empty input, got: %v", err)
    }
    if result != expected {
        t.Errorf("expected %v, got %v", expected, result)
    }
}
```

**Python:**
```python
def test_handles_empty_input():
    # This test should FAIL before fix, PASS after
    result = process_data("")
    assert result is not None
    assert result == expected
```

#### 2. Implement Fix

- Address ROOT CAUSE identified in Phase 1
- ONE change
- No "while I'm here" improvements

#### 3. Verify

- [ ] New test passes
- [ ] Existing tests still pass
- [ ] Issue actually resolved (not just the test passing)
- [ ] For IaC: `plan` shows expected changes and nothing else

#### 4. If Fix Doesn't Work

| Fix attempts | Action                                     |
| ------------ | ------------------------------------------ |
| 1-2          | Return to Phase 1 with new information     |
| 3+           | STOP -- question architecture (see below)  |

#### 5. After 3+ Failed Fixes: Question Architecture

Pattern indicating an architectural problem:

- Each fix reveals new coupling or shared state
- Fixes require "massive refactoring"
- Each fix creates new symptoms elsewhere
- For IaC: circular dependencies, state conflicts

**STOP and ask the user:**

- Is this pattern fundamentally sound?
- Should we refactor vs. continue patching?
- Do we need to discuss with the team before more fix attempts?

## Red Flags -- STOP Immediately

If you catch yourself thinking:

| Don't                                          | Do                                         | Why                                    |
| ---------------------------------------------- | ------------------------------------------ | -------------------------------------- |
| "Quick fix for now, investigate later"         | Investigate NOW                            | You never will investigate later       |
| "Just try changing X"                          | Form a hypothesis first                    | That's guessing, not debugging         |
| "I'll add multiple fixes and test"             | ONE change at a time                       | Can't isolate what worked              |
| "I don't fully understand but this might work" | Understand the root cause first            | Guessing compounds the problem         |
| "One more fix attempt" (after 2+ failures)     | STOP, reassess approach entirely           | 3+ failures means wrong approach       |
| "Let me just restart the service"              | Find out WHY the service needs a restart   | Masking symptoms                       |

**ALL mean: STOP. Return to Phase 1.**

## Language-Specific Debugging Tools

### Go

```bash
# Delve debugger
dlv debug ./cmd/server -- --flag=value    # Debug a binary
dlv test ./pkg/handler                     # Debug tests
dlv attach <pid>                           # Attach to running process

# Static analysis
go vet ./...                               # Find suspicious constructs
go vet -composites=false ./...             # Skip specific checks
staticcheck ./...                          # Extended static analysis

# Stack traces and profiling
GOTRACEBACK=all ./binary                   # Full goroutine dumps on panic
curl http://localhost:6060/debug/pprof/    # pprof over HTTP
go tool pprof cpu.prof                     # Analyze CPU profile
go tool pprof -http=:8080 mem.prof         # Memory profile in browser

# Race detection
go test -race ./...                        # Find data races
go build -race ./cmd/server                # Race-detecting binary
```

### Python

```bash
# pdb debugger
python -m pdb script.py                    # Run with debugger
# In code: import pdb; pdb.set_trace()     # Breakpoint (3.6 and below)
# In code: breakpoint()                    # Breakpoint (3.7+)

# Pytest debugging
pytest -x --tb=long                        # Stop first failure, long traceback
pytest -x --tb=short -v                    # Verbose with short traceback
pytest --lf                                # Re-run only last failures
pytest -k "test_name" -x --pdb            # Drop into debugger on failure

# Traceback and logging
python -X tracemalloc script.py            # Track memory allocations
python -W error script.py                  # Turn warnings into errors
python -c "import traceback; traceback.print_exc()"
```

### Terraform

```bash
# Debug logging
TF_LOG=DEBUG terraform plan                # Full debug output
TF_LOG=TRACE terraform apply               # Maximum verbosity
TF_LOG_PATH=./terraform.log terraform plan # Log to file

# State inspection
terraform state list                       # All resources in state
terraform state show <resource>            # Detail for one resource
terraform state pull > state.json          # Export state for inspection

# Targeted operations
terraform plan -target=<resource>          # Plan for one resource only
terraform refresh                          # Sync state with real infra
terraform import <resource> <id>           # Import existing resource

# Provider debugging
TF_LOG_PROVIDER=DEBUG terraform plan       # Provider-level debug only
```

### Pulumi

```bash
# Debug logging
pulumi up --debug                          # Debug output during update
pulumi preview --debug                     # Debug output during preview
PULUMI_DEBUG_COMMANDS=1 pulumi up          # Command-level debugging

# State inspection
pulumi stack export > stack.json           # Export full stack state
pulumi stack export | jq '.deployment.resources[] | .urn' # List resource URNs
pulumi state unprotect <urn>               # Unprotect before deletion

# Targeted operations
pulumi up --target <urn>                   # Update single resource
pulumi refresh                             # Sync state with real infra
pulumi up --replace <urn>                  # Force replacement
```

## Quick Reference

| Phase             | Key Question                          | Success Criteria                   |
| ----------------- | ------------------------------------- | ---------------------------------- |
| 1. Root Cause     | "WHY is this happening?"              | Understand cause, not just symptom |
| 2. Pattern        | "What's different from working code?" | Identified key differences         |
| 3. Hypothesis     | "Is my theory correct?"               | Confirmed or formed new theory     |
| 4. Implementation | "Does the fix work?"                  | Test passes, issue resolved        |
