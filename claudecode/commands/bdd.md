---
description: Orchestrate BDD flow — define behaviors before implementation
---

# BDD

Override work level detection and use BDD workflow for this task.

## When to Use

- Agent detected `task` but the work is actually a feature
- You want discovery/scenarios before implementation
- Task will require multiple test scenarios across files

## Behavior

1. Switch to `bdd-orchestrating` skill
2. Run through BDD phases: intake → define-behavior → scenario-gate → decomposition → implement → done
3. If a Linear issue exists, create sub-issues for phases and sync status
4. If no Linear issue, track locally in project files

## Example

```text
User: Change the auth flow to use OAuth
Agent: Task. Writing tests first. `/bdd` to override.
User: /bdd
Agent: Feature. Defining behaviors first...
       What's the goal? What should users be able to do?
```
