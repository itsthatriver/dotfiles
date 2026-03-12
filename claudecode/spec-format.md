# Spec Artifact Format

Canonical definition of the spec artifact used in spec-driven development.

## File Locations

| Artifact | Location | Created by |
|----------|----------|------------|
| Spec file | `.project/specs/<slug>.md` | `/build-spec` |
| Spec tests | Project test directory, convention-named | `/codify-spec` |

## Template

```markdown
---
status: draft  # draft | reviewed | codified | validated
---

# <Feature Name>

## Intent
Why this exists. What problem it solves. 1-3 sentences.

## Behaviors
Numbered list of observable behaviors. Each is a plain-English statement
that /codify-spec converts to an executable test case.

1. When X happens, the system does Y.
2. Given A, if B occurs, the result is C.

## Constraints
Invariants that must hold across all behaviors.

## Edge Cases
Boundary conditions. Each maps to a behavior but highlights unusual inputs or states.

## Non-Goals
What this spec explicitly does NOT cover.
```

## Section Guide

| Section | Purpose | Who writes | Who reads |
|---------|---------|------------|-----------|
| Intent | Ground truth for why the feature exists | `/build-spec` (from user interview) | Everyone |
| Behaviors | Observable outcomes that become tests | `/build-spec`, refined by `/review-spec` | `/codify-spec` |
| Constraints | Invariants across all behaviors | `/build-spec`, refined by `/review-spec` | `/codify-spec`, implementer |
| Edge Cases | Boundary conditions worth explicit tests | `/review-spec` | `/codify-spec` |
| Non-Goals | Scope fence — prevents creep | `/build-spec` | Implementer, reviewer |

## Lifecycle

```text
(none) → draft → reviewed → codified → validated
         ↑         ↑           ↑
     /build-spec  /review-spec  /codify-spec → /review-spec-tests
```

- **draft**: Created by `/build-spec` interview. Not yet stress-tested.
- **reviewed**: `/review-spec` has surfaced ambiguity, missing edges, unclear behaviors.
- **codified**: `/codify-spec` has generated executable tests from the spec.
- **validated**: `/review-spec-tests` has adversarially reviewed spec + tests.

Backward transitions are valid — new information (bugs, requirement changes) resets status
to an earlier stage via `/update-spec` (future skill).

## Examples

### Minimal

```markdown
---
status: draft
---

# User Logout

## Intent
Allow users to end their authenticated session from any page.

## Behaviors
1. When a logged-in user clicks "Log out", their session is invalidated.
2. After logout, the user is redirected to the login page.
3. After logout, subsequent requests with the old session token return 401.

## Constraints
- Logout must complete within 2 seconds.

## Edge Cases
- User clicks logout twice rapidly (idempotent — second click is a no-op).

## Non-Goals
- "Log out all devices" (separate feature).
```

### Comprehensive

```markdown
---
status: reviewed
---

# Webhook Retry Policy

## Intent
Ensure webhook deliveries are reliably retried on failure so consumers
don't miss events due to transient errors.

## Behaviors
1. When a webhook delivery receives a 5xx response, the system schedules a retry.
2. Retries use exponential backoff: 1m, 5m, 30m, 2h, 24h.
3. After 5 failed attempts, the webhook is marked as "failed" and no further retries occur.
4. When a retry succeeds, the webhook status is updated to "delivered".
5. Each delivery attempt is logged with timestamp, response code, and attempt number.
6. When the target endpoint returns 410 Gone, the webhook subscription is auto-disabled.

## Constraints
- Retry scheduling must survive process restarts (persistent queue).
- Concurrent retries for the same event are not allowed.
- Delivery log retention: 30 days.

## Edge Cases
- Target returns 301 redirect (follow up to 3 redirects, then fail).
- Target returns 200 but response body indicates error (treat as success — we honor status codes).
- Webhook payload exceeds 1MB (reject at creation time, not at delivery).
- Clock skew between scheduler and worker (use monotonic ordering, not wall clock).

## Non-Goals
- Fan-out to multiple endpoints per event (separate feature).
- Webhook signature rotation (covered by auth spec).
- Custom retry policies per subscriber.
```
