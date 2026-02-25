# Phase 5: Technical Decomposition

**Entry:** Agent enters `decomposition` phase (after scenarios validated via AOD gate).

---

## Step 1: Identify Components

Analyze validated scenarios and identify what parts of the system each one touches.

### Component Categories

| Category          | Examples                                              |
|-------------------|-------------------------------------------------------|
| **Data models**   | Structs, schemas, database tables, state files        |
| **Business logic**| Pure functions, validation, transformation, computation |
| **API layer**     | HTTP handlers, gRPC services, CLI commands, module interfaces |
| **External deps** | Database calls, API clients, cloud provider APIs      |
| **Glue/wiring**   | Dependency injection, configuration, routing, provider blocks |

### IaC Component Mapping

For infrastructure as code projects, components map differently:

| IaC Concept           | Component Equivalent         | Example                           |
|-----------------------|------------------------------|-----------------------------------|
| **Module**            | Component                    | `modules/vpc/`, `modules/s3/`     |
| **Resource**          | Implementation unit          | `aws_s3_bucket`, `google_compute_instance` |
| **Variable**          | Input interface              | `variable "cidr_block" {}`        |
| **Output**            | Output contract              | `output "bucket_arn" {}`          |
| **Data source**       | External dependency          | `data "aws_caller_identity" {}`   |
| **Provider config**   | Glue/wiring                  | `provider "aws" { region = ... }` |
| **Pulumi Component**  | Component                    | `class VpcComponent(ComponentResource)` |
| **Stack**             | Integration boundary         | `Pulumi.dev.yaml`                 |

---

## Step 2: Assign Test Layers

For each component, determine the appropriate test layer:

### Test Layer Decision Tree

```
Does this component have external dependencies (network, disk, cloud API)?
  NO  --> UNIT TEST
          Pure logic, fast, no setup required
  YES --> Does this test a boundary between two components?
            YES --> INTEGRATION TEST
                    Tests the contract between components
            NO  --> Does this test full user/system behavior end-to-end?
                      YES --> E2E TEST
                              Full system, real (or staging) environment
                      NO  --> INTEGRATION TEST
                              Component + its external dependency
```

### Test Layer Matrix

| Layer           | What It Tests                | Speed    | Dependencies               |
|-----------------|------------------------------|----------|-----------------------------|
| **Unit**        | Pure logic, no external deps | Fast     | None (mocks if needed)      |
| **Integration** | Module boundaries, contracts | Medium   | Real deps or test doubles   |
| **E2E**         | Full system behavior         | Slow     | Full environment            |

### Test Runners by Language

| Language     | Unit                    | Integration                  | E2E                          |
|--------------|-------------------------|------------------------------|------------------------------|
| **Go**       | `go test ./...`         | `go test -tags=integration`  | `go test -tags=e2e`         |
| **Python**   | `pytest tests/unit/`    | `pytest tests/integration/`  | `pytest tests/e2e/`         |
| **OpenTofu** | `tofu test` (plan mode) | `tofu test` (apply to test)  | Deploy to staging + validate |
| **Pulumi**   | Language-specific unit test runner | `pulumi up` to test stack | Deploy to staging + validate |
| **Shell**    | Function-level tests (bats) | Script-level tests (bats)  | Full workflow tests          |

### IaC Test Layer Details

| Layer           | OpenTofu                              | Pulumi                                |
|-----------------|---------------------------------------|---------------------------------------|
| **Unit**        | `tofu test` with `mock_provider` blocks; plan-only mode; validate resource attributes in plan | Unit tests with mock monitor; assert resource count, properties, URNs |
| **Integration** | `tofu test` with real apply to isolated test account; validate resource creation and outputs | `pulumi up` to test stack with Automation API; validate stack outputs |
| **E2E**         | Apply to staging environment; run external validation (curl, API calls, smoke tests) | Deploy to staging stack; run acceptance tests against live infrastructure |

---

## Step 3: Create Task Breakdown

Order tasks by dependencies. Build from the bottom up:

### Standard Ordering

```
1. Data models / schemas / types       (no dependencies)
2. Business logic / pure functions      (depends on: models)
3. API layer / handlers / CLI           (depends on: logic + models)
4. Integration wiring                   (depends on: all above)
5. E2E validation                       (depends on: everything)
```

### IaC Ordering

```
1. Variable definitions / inputs        (no dependencies)
2. Data sources / lookups               (depends on: variables)
3. Core resources                       (depends on: variables + data)
4. Dependent resources                  (depends on: core resources)
5. Outputs                              (depends on: all resources)
6. Module integration / root module     (depends on: child modules)
```

### Task Format

For each task, document:

```markdown
### Task {N}: {descriptive name}

- **Component:** {component name}
- **Test layer:** unit | integration | e2e
- **Depends on:** Task {M}, Task {K} (or "none")
- **Scenarios covered:** Scenario 1, Scenario 3
- **Estimated complexity:** small | medium | large
```

### Complexity Heuristics

| Size     | Indicators                                    | Typical Scope          |
|----------|-----------------------------------------------|------------------------|
| **Small**  | 1 file, <50 lines, well-understood pattern  | Single function + test |
| **Medium** | 2-3 files, new pattern or interface          | Module + tests         |
| **Large**  | 4+ files, new external integration, state management | Full component  |

---

## Step 4: Present to User

Show the decomposition as a dependency graph:

```
Task 1: Define user model (unit) ----+
                                      |
Task 2: Validation logic (unit) ------+---> Task 4: HTTP handler (integration)
                                      |
Task 3: Database adapter (unit) ------+---> Task 5: E2E user creation flow
```

Ask user to confirm or adjust ordering.

---

## Complex Features

If the decomposition reveals significant complexity:

| Signal                         | Suggestion                              |
|--------------------------------|-----------------------------------------|
| 5+ major components            | Consider splitting (see SKILL.md)       |
| New technology choice needed   | Document decision in ticket before implementing |
| Schema/state migration required | Add migration task as dependency for all others |
| Cross-cutting concern (auth, logging) | Extract as shared utility first  |

---

## Phase 5 Exit (Required)

Before proceeding to Phase 6 (implement):

### Local Tracking

1. Task breakdown documented in ticket.md under `## Decomposition`
2. Update frontmatter: `phase: implement`
3. Log: `Complete: Phase 5 - Decomposed into {N} tasks`

### Linear Tracking

1. Update `[BDD:Decomposition]` sub-issue to Done
2. Create implementation sub-issues for each task (or component group)
3. Add comment to parent issue: "Decomposition complete. {N} tasks identified. Starting implementation."
