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
| DONE_WITH_CONCERNS | Address concerns before review. Note observations, decide whether to act. |
| NEEDS_CONTEXT | Provide missing information, re-dispatch |
| BLOCKED | Assess: provide context, break down task, or escalate to user |

Never force retry without changing inputs.

## Anti-Patterns

- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
