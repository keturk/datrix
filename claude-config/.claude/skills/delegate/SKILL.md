---
description: Delegate tasks to background agents with two-stage review and model selection
model: haiku
disable-model-invocation: true
---

# Delegating to Background Agents

## Agent Output Persistence

Always persist agent output to disk:
1. Create a session subfolder: `d:/datrix/.agent_output/<date>-<task>/`
2. Give each agent a unique filename: `agent-<role>-<number>.md`

## Model Selection

Pick the least powerful model that fits the task:

| Task type | Model | Examples |
|---|---|---|
| Mechanical | haiku | Isolated function, clear spec, 1-2 files, renames, formatting |
| Integration | sonnet | Multi-file coordination, pattern matching, template changes |
| Architecture/review | opus | Design decisions, cross-cutting concerns, complex debugging |

## Dispatch

For each task, construct exactly the context the agent needs — don't let it inherit session bloat. Include:
- What to do (specific, complete)
- Which files to read/modify (exact paths)
- Constraints and anti-patterns to avoid
- How to verify (test commands, expected output)

Max 1 agent for reviews. Max 2-3 for write-heavy tasks. Wait for completion before launching more.

## Two-Stage Review

After an agent completes implementation, review in two passes:

**Stage 1 — Spec compliance:** Does the output match requirements? Correct files modified? All cases handled? Nothing missing?

**Stage 2 — Code quality:** Does the code follow project standards? Types, logging, error messages, complexity, no anti-patterns?

Do not combine stages. Spec issues mask quality issues and vice versa.

## Agent Status Handling

Every completed agent must return evidence for each claimed check as the exact command it ran plus the actual pasted output — never a bare "passed"/"green" — so you can trust the result without re-running it yourself.

| Status | Action |
|---|---|
| DONE | Proceed to review |
| EXPANSION_REQUIRED | The agent knows the fix but needs a file lock. Re-dispatch it serially once the files are free. Not a failure. |
| NEEDS_CONTEXT | Provide missing information, re-dispatch |
| BLOCKED | **Validate the proof first** (execution-contract §3): verbatim error text + a fix actually written and run (`file:line`) + why it failed + a `B1`–`B4` code. **Missing any → reject and re-dispatch**, quoting the report back. Only a *proven* blocker is terminal. |

**`DONE_WITH_CONCERNS` has been removed.** It was a licensed way to hand back unfinished work with a shrug. A concern is either a defect you fix, a defect you file as a tracked task, or a proven B1–B4 blocker — there is no fourth bucket.

Never force retry without changing inputs.

## Anti-Patterns

- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
