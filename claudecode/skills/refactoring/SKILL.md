---
name: refactoring
description: Systematic refactoring with small-step discipline. Use when user says 'refactor', 'clean up', 'restructure', 'extract', 'rename', 'simplify', or mentions code smells. Enforces one change → test → commit cycle. NOT for adding features or fixing bugs.
allowed-tools: '*'
---

# Systematic Refactoring

One change. Test. Commit. Repeat.

**Iron Law:** ONE REFACTORING --> TEST --> COMMIT. Never batch.

## When to Use

Answer IN ORDER. Stop at first match:

1. User says "refactor", "clean up", "restructure"? --> Use this skill
2. User says "extract", "rename", "simplify"? --> Use this skill
3. Code smell identified during review? --> Use this skill
4. User wants a new feature? --> Skip (not refactoring)
5. User wants a bug fix? --> Skip (use debugging skill)
6. User wants formatting only? --> Skip (use linting tools)

## Code Smells That Trigger Refactoring

- Duplicated logic across functions or modules
- Functions longer than ~40 lines
- Magic numbers or string literals
- Deep nesting (3+ levels)
- Dead code or unreachable branches
- Poor naming that obscures intent
- God objects or functions doing too many things
- Long parameter lists (4+)
- Feature envy (function uses another module's data more than its own)

## The Five Phases

### Phase 1: Assess

**Is this actually refactoring?**

| Request                          | Verdict          | Reason                              |
| -------------------------------- | ---------------- | ----------------------------------- |
| "Extract this into a function"   | Refactoring      | Structure change, same behavior     |
| "Rename these variables"         | Refactoring      | Clarity change, same behavior       |
| "Add validation to this input"   | NOT refactoring  | New behavior (use feature workflow)  |
| "Fix this nil pointer crash"     | NOT refactoring  | Bug fix (use debugging skill)        |
| "Format this file"               | NOT refactoring  | Formatting (use linter/formatter)    |
| "Remove this unused function"    | Refactoring      | Dead code removal, same behavior     |
| "Split this into smaller files"  | Refactoring      | Structure change, same behavior      |

If not refactoring, redirect to the correct skill. Do not proceed.

### Phase 2: Protect

**Verify test coverage BEFORE making any changes.**

#### Check Existing Coverage

**Go:**
```go
// Run coverage for the package being refactored
// go test -cover ./pkg/handler/...
// go test -coverprofile=coverage.out ./pkg/handler/...
// go tool cover -func=coverage.out
```

**Python:**
```python
# Run coverage for the module being refactored
# pytest --cov=src/handler tests/ --cov-report=term-missing
```

#### Add Characterization Tests If Coverage Is Missing

Characterization tests capture CURRENT behavior, not desired behavior. They exist to detect unintended changes during refactoring.

**Go:**
```go
func TestProcessOrder_CurrentBehavior(t *testing.T) {
    // Characterization test: captures what the code ACTUALLY does
    // before refactoring. If this fails after refactoring,
    // behavior changed unintentionally.
    input := Order{
        Items:    []Item{{Name: "widget", Qty: 3, Price: 1099}},
        Discount: 10,
    }

    result, err := ProcessOrder(input)

    require.NoError(t, err)
    assert.Equal(t, 2967, result.Total)     // 3 * 1099 = 3297, minus 10% = 2967
    assert.Equal(t, "pending", result.Status)
    assert.Len(t, result.LineItems, 1)
}
```

**Python:**
```python
def test_process_order_current_behavior():
    """Characterization test: captures what the code ACTUALLY does
    before refactoring. If this fails after refactoring,
    behavior changed unintentionally."""
    order = Order(
        items=[Item(name="widget", qty=3, price=1099)],
        discount=10,
    )

    result = process_order(order)

    assert result.total == 2967  # 3 * 1099 = 3297, minus 10% = 2967
    assert result.status == "pending"
    assert len(result.line_items) == 1
```

**Do not proceed to Phase 3 until tests exist and pass.**

### Phase 3: Refactor

Apply ONE technique from the catalog below. Smallest scope first.

#### Refactoring Catalog

##### Tier 1: Always Safe

Mechanical transformations. Very low risk of behavior change.

**Rename (variable, function, type, file)**

*Go -- before:*
```go
func calc(d []float64) float64 {
    t := 0.0
    for _, v := range d {
        t += v
    }
    return t / float64(len(d))
}
```

*Go -- after:*
```go
func calculateMean(measurements []float64) float64 {
    sum := 0.0
    for _, value := range measurements {
        sum += value
    }
    return sum / float64(len(measurements))
}
```

*Python -- before:*
```python
def calc(d):
    t = 0
    for v in d:
        t += v
    return t / len(d)
```

*Python -- after:*
```python
def calculate_mean(measurements: list[float]) -> float:
    total = 0.0
    for value in measurements:
        total += value
    return total / len(measurements)
```

**Extract Function**

*Go -- before:*
```go
func CreateUser(name, email string) (*User, error) {
    // validation mixed with creation
    if name == "" {
        return nil, fmt.Errorf("name required")
    }
    if !strings.Contains(email, "@") {
        return nil, fmt.Errorf("invalid email")
    }
    if len(name) > 100 {
        return nil, fmt.Errorf("name too long")
    }

    user := &User{Name: name, Email: email}
    return user, nil
}
```

*Go -- after:*
```go
func validateUserInput(name, email string) error {
    if name == "" {
        return fmt.Errorf("name required")
    }
    if !strings.Contains(email, "@") {
        return fmt.Errorf("invalid email")
    }
    if len(name) > 100 {
        return fmt.Errorf("name too long")
    }
    return nil
}

func CreateUser(name, email string) (*User, error) {
    if err := validateUserInput(name, email); err != nil {
        return nil, err
    }
    user := &User{Name: name, Email: email}
    return user, nil
}
```

*Python -- before:*
```python
def create_user(name: str, email: str) -> User:
    if not name:
        raise ValueError("name required")
    if "@" not in email:
        raise ValueError("invalid email")
    if len(name) > 100:
        raise ValueError("name too long")

    return User(name=name, email=email)
```

*Python -- after:*
```python
def _validate_user_input(name: str, email: str) -> None:
    if not name:
        raise ValueError("name required")
    if "@" not in email:
        raise ValueError("invalid email")
    if len(name) > 100:
        raise ValueError("name too long")


def create_user(name: str, email: str) -> User:
    _validate_user_input(name, email)
    return User(name=name, email=email)
```

**Extract Variable / Inline Variable / Move Function**

These are mechanical. Apply when a complex expression needs a name, a variable adds no clarity, or a function belongs in a different package or module.

##### Tier 2: Safe With Tests

Require existing test coverage to verify behavior preservation.

**Decompose Conditional**

*Go -- before:*
```go
func CalculatePrice(order Order) int {
    if order.IsMember && order.Total > 10000 && !order.HasUsedDiscount {
        return int(float64(order.Total) * 0.85)
    } else if order.IsMember {
        return int(float64(order.Total) * 0.90)
    } else {
        return order.Total
    }
}
```

*Go -- after:*
```go
func qualifiesForPremiumDiscount(order Order) bool {
    return order.IsMember && order.Total > 10000 && !order.HasUsedDiscount
}

func CalculatePrice(order Order) int {
    if qualifiesForPremiumDiscount(order) {
        return int(float64(order.Total) * 0.85)
    }
    if order.IsMember {
        return int(float64(order.Total) * 0.90)
    }
    return order.Total
}
```

**Replace Guard Clauses**

*Python -- before:*
```python
def process_payment(payment: Payment) -> Result:
    if payment is not None:
        if payment.amount > 0:
            if payment.method in VALID_METHODS:
                # actual logic buried under nesting
                return charge(payment)
            else:
                return Result(error="invalid method")
        else:
            return Result(error="invalid amount")
    else:
        return Result(error="no payment")
```

*Python -- after:*
```python
def process_payment(payment: Payment) -> Result:
    if payment is None:
        return Result(error="no payment")
    if payment.amount <= 0:
        return Result(error="invalid amount")
    if payment.method not in VALID_METHODS:
        return Result(error="invalid method")

    return charge(payment)
```

**Replace Magic Literal / Remove Dead Code**

Replace unexplained numbers and strings with named constants. Remove code that is never called.

##### Tier 3: Requires Care

Higher risk. Verify thoroughly. Consider discussing with the user first.

| Technique                        | Risk     | When to use                                     |
| -------------------------------- | -------- | ----------------------------------------------- |
| Extract Class / Module           | Medium   | God object or module doing too many things       |
| Replace with Polymorphism        | Medium   | Long switch/if-else chains on type               |
| Introduce Parameter Object       | Medium   | Functions with 4+ related parameters             |
| Collapse Hierarchy               | High     | Inheritance chain adds no value                  |
| Replace Inheritance with Comp.   | High     | "is-a" should be "has-a"                         |

For Tier 3, write the plan out before executing. Get user confirmation on large structural changes.

### Phase 4: Verify

After EACH individual refactoring step:

```bash
# Go
go test ./...
go vet ./...

# Python
pytest
```

| Test result | Action                                         |
| ----------- | ---------------------------------------------- |
| All green   | Commit this step immediately                   |
| Any red     | Revert this step. Do NOT attempt to fix it.    |

**Commit message format:**

```
refactor: <what you did>

<why, in one sentence>
```

Example:
```
refactor: extract validateUserInput from CreateUser

Separate validation from construction for testability
```

### Phase 5: Iterate

1. Return to Phase 3 for the next refactoring step
2. After all steps complete, run full audit:
   - Full test suite
   - Linter / static analysis
   - Check for dead code introduced during refactoring
   - Verify no behavior changes leaked through

## Anti-Patterns -- What NOT to Do

| Anti-Pattern                     | Problem                                      | Instead                                       |
| -------------------------------- | -------------------------------------------- | --------------------------------------------- |
| Big Bang refactor                | Too many changes to isolate failures          | One step at a time                            |
| Refactor without tests           | No safety net to detect behavior changes      | Add characterization tests first              |
| "Fix" a failing refactor step    | Compounds the problem, introduces new bugs    | Revert and try a different approach           |
| Refactor + feature in one commit | Can't tell what changed behavior              | Separate commits: refactor first, feature second |
| Refactor code you don't understand | High chance of breaking hidden assumptions  | Read and understand first, add tests, then refactor |
| Premature abstraction            | Adds complexity without proven benefit        | Wait for the third duplication (Rule of Three) |
| Renaming everything at once      | Massive diff, impossible to review            | Rename one symbol per commit                  |
| Skipping the revert              | Broken test means behavior changed            | Always revert on red, no exceptions           |

## When to Stop

| Situation                           | Action                                           |
| ----------------------------------- | ------------------------------------------------ |
| Tests pass after a step             | Commit and continue to next step                 |
| Tests fail after a step             | Revert immediately                               |
| 2 failed attempts at the same step  | STOP. Ask the user for guidance.                 |
| Refactoring reveals a bug           | STOP refactoring. File bug. Use debugging skill. |
| Scope is growing beyond original ask | STOP. Confirm expanded scope with user.          |
| You're unsure if behavior changed    | STOP. Write a more specific test, then continue. |

## Quick Reference

| Phase       | Key Question                           | Success Criteria                        |
| ----------- | -------------------------------------- | --------------------------------------- |
| 1. Assess   | "Is this actually refactoring?"        | Confirmed: structure change, same behavior |
| 2. Protect  | "Do tests cover this code?"            | Tests exist and pass                    |
| 3. Refactor | "What is the ONE smallest change?"     | Applied single technique                |
| 4. Verify   | "Do tests still pass?"                 | Green = commit, Red = revert            |
| 5. Iterate  | "Is there more to do?"                 | All steps done, full audit passes       |
