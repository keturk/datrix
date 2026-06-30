# Agent Progress Polling Protocol

Shared protocol for any skill that delegates work to background agents
(`/task-orchestrator`, `/execute-tasks-parallel`, `/execute-tasks`). It replaces the
**completion-notification** model — where the orchestrator dispatches an agent and then waits
passively for a `<task-notification>` to fire (and, in the meantime, assumes the agent "is
working") — with an **active, evidence-based polling** model.

## Core Principle

**Never assume a delegated agent is making progress, and never depend on a completion
notification arriving.** Every ~5 minutes, perform a *genuine* check of what each in-flight
agent is actually doing — backed by observable evidence (its reported status **and** the files
it is supposed to be producing on disk), not by the mere absence of a failure or notification.

A completion notification, if one happens to arrive, is a convenience that may trigger an
earlier poll. It is **never required and never trusted on its own** — the poll's genuine check
is the authoritative source of truth.

## Dispatch in Background

Spawn each delegated agent with `run_in_background: true` so it can be polled while it runs.
A foreground agent blocks the orchestrator completely and cannot be checked, so background
dispatch is **mandatory** for this protocol. When you dispatch, record for each agent:

- `task_id` — the background task id returned by the Agent tool (used by `TaskOutput` / `TaskStop`)
- the task being implemented (e.g. `task-34-01`)
- its assigned `files_to_create` and `files_to_modify` (from the task file) — these are the
  artifacts you will check on disk to verify real work

Initialize a per-agent **artifact snapshot** at dispatch time: for each assigned file, record
whether it exists and its current line count (0 if absent).

## Poll Loop (every ~5 minutes)

Repeat until every delegated agent has reached a terminal state (completed / blocked / failed):

### 1. Bounded wait + harvest (paces the loop at 5 minutes)

Pick one still-in-flight agent and call:

```
TaskOutput(task_id=<that agent>, block=true, timeout=300000)
```

- **Returns a completed result** → that agent finished. Parse its JSON result, mark it terminal,
  free its slot. Then continue to step 2 to check the rest.
- **Times out (5 minutes elapsed, agent still running)** → proceed to step 2.

Do **not** use a foreground `sleep` to pace the loop — the harness blocks foreground sleeps.
The 5-minute `TaskOutput` timeout *is* the pacing mechanism, and it doubles as a harvest of any
agent that finished during the interval.

### 2. Genuine on-disk evidence sweep (the authoritative progress check)

For **every** agent still marked in-flight, independently verify it is doing real work by
inspecting the artifacts it is supposed to produce — this costs almost no context and cannot be
faked by a stuck agent:

- Line-count / `stat` each of the agent's `files_to_create` and `files_to_modify`.
- Diff against the agent's snapshot from the previous poll: did any assigned file get created,
  grow, or change mtime since last time?

This filesystem diff — not a status string, and not the absence of a notification — is the
genuine "what is this agent actually doing right now" signal.

### 3. Classify each in-flight agent and act

- **Completed** — harvested in step 1, or its assigned files show the task's work is done and a
  follow-up `TaskOutput(task_id, block=false)` confirms terminal status → parse result, free
  slot, hand back to the skill's normal post-completion handling (result collection, refill,
  advance).
- **Genuinely progressing** — status is running **and** at least one assigned artifact advanced
  since the last poll → leave it running. Save this poll's artifact snapshot for the next diff.
- **Stalled** — no assigned artifact changed across **two consecutive polls (~10 min)**, *or*
  status indicates it is waiting on input the orchestrator never sent. Treat this as a problem,
  **not** as silent progress:
  - Do a targeted `TaskOutput(task_id, block=false)` to read why it is stuck (a question, a loop,
    an error). (See the context caveat below — only do this for suspected-terminal/stalled
    agents, not for every agent every cycle.)
  - If it is waiting on a genuine question → relay via the skill's question path (`AskUserQuestion`
    or the Decision Escalation Protocol) and re-dispatch with the answer.
  - If it is genuinely hung or looping with no progress → `TaskStop(task_id)` it, then re-dispatch
    with corrective context or mark it BLOCKED. Never leave a stalled agent counted as in-flight
    indefinitely.
- **Errored / crashed / hit max_turns** → mark BLOCKED, free its slot, handle per the skill's
  failure path.

### 4. Heartbeat

Emit a one-line, evidence-based status so the user sees a genuine check each cycle:

```
Poll {n} (T+{mm}m): {k} running, {c} done, {s} stalled | running: {task_id}↑{lines added since last poll} ...
```

The `↑lines` figure comes from the step-2 on-disk diff — it is proof the agent did real work this
interval, not an assumption.

### 5. Repeat

Loop back to step 1 with the still-in-flight set. The pool/sequence refill happens through the
owning skill's normal logic as slots free up.

## Hard Rules

- **Never** report an agent as "working" / "in progress" without having checked, this cycle,
  both its status **and** its on-disk artifacts.
- **Never** wait indefinitely on a single `TaskOutput(block=true)` — cap every wait at the
  5-minute `timeout` so one dead agent cannot hang the whole run.
- **Never** treat the absence of a completion notification as evidence of progress. Absence of a
  notification is absence of information; the poll is what produces information.
- **Two-consecutive-poll stall rule:** an agent whose assigned files have not changed across two
  polls (~10 minutes) is investigated, not assumed to be thinking.

## Context Caveat — `TaskOutput` on agent tasks

For a background **agent** task, `TaskOutput` may return a large slice of the subagent's
conversation transcript, which can flood the orchestrator's context. Therefore:

- Use the **step-2 on-disk artifact diff as the primary progress signal** — it is cheap and
  context-free.
- Reserve `TaskOutput(task_id, block=false)` for agents you already suspect are terminal or
  stalled (to harvest a result or read why they are stuck) — do **not** call it on every agent
  every cycle.
- Never `Read` an agent task's `.output` file directly — it is a symlink to the full JSONL
  transcript and will overflow context. Use the harvested `TaskOutput` result or the Agent tool
  result instead.