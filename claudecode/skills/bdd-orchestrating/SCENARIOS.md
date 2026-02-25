# Phase 3-4: Define Behavior & Scenario Gate

---

## Phase 3: Define Behavior

**Entry:** Agent enters `define-behavior` phase (after discovery or resume).

### 3.1 Draft Scenarios

1. Read spec goal/scope (from ticket.md or Linear issue)
2. Draft Given/When/Then scenarios covering three categories:

| Category        | Description                                | Minimum Count |
|-----------------|--------------------------------------------|---------------|
| **Happy path**  | Main success flow, expected inputs          | 1-2           |
| **Failure modes** | Error handling, invalid inputs, timeouts  | 2-3           |
| **Edge cases**  | Boundaries, empty states, concurrent access | 1-2           |

3. Present scenarios to user for review
4. User can add, modify, or remove scenarios
5. Each scenario gets a `[ ]` checkbox for implementation tracking

### 3.2 Scenario Format

Use standard Given/When/Then with language-generic assertions:

```markdown
## Scenario: [descriptive name]

**Given** [initial context / preconditions]
**When** [action or event occurs]
**Then** [expected observable outcome]

Test layer: [unit | integration | e2e]
Component: [what part of the system this tests]
```

### Language-Specific Scenario Examples

**Go (HTTP handler):**
```markdown
## Scenario: Valid request returns user profile

Given a user with ID "abc123" exists in the store
When GET /users/abc123 is called
Then the response status is 200
  And the response body contains the user's email

Test layer: integration
Component: user handler
```

**Python (data pipeline):**
```markdown
## Scenario: Pipeline handles missing columns gracefully

Given a CSV file with columns [name, email] but missing [phone]
When the pipeline processes the file
Then the phone column is filled with empty strings
  And a warning is logged with the missing column names

Test layer: unit
Component: column normalizer
```

**OpenTofu (module):**
```markdown
## Scenario: S3 bucket created with versioning enabled

Given the module is called with versioning = true
When tofu plan is run
Then the plan shows an aws_s3_bucket resource with versioning enabled
  And the plan shows an aws_s3_bucket_versioning resource

Test layer: unit (tofu test, plan mode)
Component: s3-bucket module
```

**Pulumi (component resource):**
```markdown
## Scenario: VPC component creates expected subnets

Given the VPC component is instantiated with cidr_block "10.0.0.0/16" and 3 AZs
When the component is deployed (unit test with mock monitor)
Then 3 public subnets and 3 private subnets are created
  And each subnet CIDR is within the VPC CIDR range

Test layer: unit
Component: vpc-component
```

**Shell (CLI tool):**
```markdown
## Scenario: Missing required argument shows usage

Given the script is invoked with no arguments
When the script runs
Then exit code is 1
  And stderr contains "Usage:"

Test layer: integration
Component: cli entrypoint
```

### 3.3 Save Scenarios

**Local tracking:**
Save to `.project/tickets/{id}-{slug}/test-definitions.md`:

```markdown
# Test Definitions: {feature name}

## Happy Path

- [ ] Scenario: [name]
  Given ...
  When ...
  Then ...

## Failure Modes

- [ ] Scenario: [name]
  Given ...
  When ...
  Then ...

## Edge Cases

- [ ] Scenario: [name]
  Given ...
  When ...
  Then ...
```

**Linear tracking:**
Add scenarios as a checklist comment on the `[BDD:Scenarios]` sub-issue:

```
Scenarios defined:
- [ ] [Scenario name 1]
- [ ] [Scenario name 2]
- [ ] [Scenario name 3]

Full definitions saved in test-definitions.md
```

### 3.4 Phase 3 Exit (Required)

1. Scenarios saved to test-definitions.md (always, even when using Linear)
2. Update phase to `scenario-gate`
3. Log: `Complete: Phase 3 - {N} scenarios defined`

---

## Phase 4: Scenario Quality Gate

**Entry:** Agent enters `scenario-gate` phase.

### AOD Quality Gate

Validate each scenario against three criteria:

| Criterion         | Check                             | Red Flag                             | Fix                                 |
|-------------------|-----------------------------------|--------------------------------------|--------------------------------------|
| **Atomic**        | Tests ONE behavior                | Multiple When/Then pairs             | Split into separate scenarios        |
| **Observable**    | Has externally visible outcome    | Only checks internal state           | Assert on output, response, or side effect |
| **Deterministic** | Same result on repeated runs      | Depends on time, randomness, external state | Mock non-deterministic inputs    |

### Validation Process

For each scenario:

```
1. Check Atomic:
   - Count the "When" clauses. More than 1? --> Split.
   - Count the "Then" clauses. More than 3? --> Probably testing multiple behaviors. Split.

2. Check Observable:
   - Does "Then" reference something a caller/user can observe?
   - BAD: "Then the internal cache is updated"
   - GOOD: "Then subsequent GET returns the cached value"

3. Check Deterministic:
   - Does the scenario depend on current time? --> Inject clock
   - Does it depend on random values? --> Inject seed or mock
   - Does it depend on external service state? --> Mock or fixture
```

### Report Format

Group issues by type and suggest fixes:

```
Scenario Quality Report:

ATOMIC issues:
  - Scenario 3: Tests login AND session creation. Split into:
    a) "Valid credentials return auth token"
    b) "Successful login creates session record"

OBSERVABLE issues:
  - Scenario 5: "Then the cache is warm" -- internal state.
    Suggest: "Then GET /resource responds in <50ms"

DETERMINISTIC issues:
  - Scenario 7: Depends on current timestamp.
    Suggest: Inject a clock interface / freeze time in test setup
```

### IaC-Specific AOD Checks

| Criterion         | IaC Red Flag                          | IaC Fix                              |
|-------------------|---------------------------------------|---------------------------------------|
| **Atomic**        | Plan creates resource AND configures IAM | Split: resource creation vs. IAM binding |
| **Observable**    | "Then the module works correctly"     | "Then plan shows N resources with specific attributes" |
| **Deterministic** | Depends on existing cloud state       | Use mock providers or isolated test accounts |

### Phase 4 Exit (Required)

Before proceeding to Phase 5:

1. Each scenario validated against AOD criteria
2. Issues reported and resolved (or confirmed clean)
3. Update phase to `decomposition`
4. Log: `Complete: Phase 4 - Scenarios validated ({N} passed, {M} fixed)`

**Linear:** Update `[BDD:Scenarios]` sub-issue to Done, add validation summary as comment.
