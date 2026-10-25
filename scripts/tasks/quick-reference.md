# Quick Reference — Task Management Scripts

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. The task/bug format, what each script checks and its module: [README.md](README.md).

`-BaseDir` (a different workspace), `-Dbg` and `-SelfTest` are accepted by every script here. Options are spelled in full (an abbreviation is a usage error, exit 2). Phase-analysis scripts write details to JSON under `D:\datrix\.tmp\tasks\` and print a one- or two-line summary plus a `Details:` path.

## `tasks\todo.ps1`

List incomplete tasks and bugs across all projects.

| Form | Command |
|------|---------|
| All | `.\tasks\todo.ps1` |
| Filter by file name or title | `.\tasks\todo.ps1 -Filter "parser"` |

Parameters: `-BaseDir` (position 0), `-Filter` (position 1), `-Dbg`, `-SelfTest`. Exit: 0 listed, 1 base directory missing.

## `tasks\complete.ps1`

Mark a task's heading `# COMPLETED: Task ...`. Add the `## How Solved` section by hand.

| Form | Command |
|------|---------|
| Absolute path | `.\tasks\complete.ps1 "D:\datrix\datrix-common\.tasks\phase-05\task-05-01.md"` |
| Relative path | `.\tasks\complete.ps1 ".tasks\phase-05\task-05-01.md"` |
| File name (searches every `.tasks/`) | `.\tasks\complete.ps1 "task-05-01.md"` |

Parameters: `-TaskFile` (position 0, required), `-Dbg`, `-SelfTest`. Exit: 0 marked or already completed, 1 not found / ambiguous / not a task title / not writable, 2 usage error.

## `tasks\completed.ps1`

List completed tasks and fixed bugs.

| Form | Command |
|------|---------|
| All | `.\tasks\completed.ps1` |
| Filter | `.\tasks\completed.ps1 -Filter "parser"` |

Parameters: `-BaseDir` (position 0), `-Filter` (position 1), `-Dbg`, `-SelfTest`. Exit: 0 listed, 1 base directory missing.

## `tasks\cleanup.ps1`

List or delete task artifacts (`task-*`, `dependencies.md`) from `.tasks/` folders. Nothing is deleted without `-Force` and a typed `yes`.

| Form | Command |
|------|---------|
| List (dry run) | `.\tasks\cleanup.ps1` |
| Delete all | `.\tasks\cleanup.ps1 -Force` |
| Delete phases before N | `.\tasks\cleanup.ps1 -Force -Phase 60` |

Parameters: `-BaseDir` (position 0), `-Force`, `-Phase` (position 1), `-Dbg`, `-SelfTest`. Exit: 0 listed / deleted / cancelled, 1 base directory missing.

## `tasks\latest-phase.ps1`

Print the highest phase number found in `.tasks/` folders (the number only).

| Form | Command |
|------|---------|
| Latest | `.\tasks\latest-phase.ps1` |
| Show every phase found | `.\tasks\latest-phase.ps1 -Dbg` |

Parameters: `-BaseDir` (position 0), `-Dbg`, `-SelfTest`. Exit: 0 done, 1 base directory missing.

## `tasks\phase-status.ps1`

Metadata snapshot of a phase's tasks across all repos → `D:\datrix\.tmp\tasks\phase-NN-status.json`. Reports live disk truth; re-run after any task-file change.

| Form | Command |
|------|---------|
| Snapshot | `.\tasks\phase-status.ps1 31` |

Parameters: phase number (positional, required), `-BaseDir`, `-Output <path>`, `-Dbg`, `-SelfTest`. Exit: 0 done, 2 usage / phase not found.

## `tasks\plan-waves.ps1`

Execution plan for one phase: topological waves, file-conflict splitting, blockers → `D:\datrix\.tmp\tasks\phase-NN-waves.json`.

| Form | Command |
|------|---------|
| Pending tasks | `.\tasks\plan-waves.ps1 31` |
| Include completed | `.\tasks\plan-waves.ps1 31 -IncludeCompleted` |

Parameters: phase number (positional, required), `-IncludeCompleted`, `-BaseDir`, `-Output <path>`, `-Dbg`, `-SelfTest`. Exit: 0 clean, 1 blockers or cycle (read the JSON), 2 usage error.

## `tasks\plan-waves-multi.ps1`

The same plan over several phases run as one batch (at least two phases).

| Form | Command |
|------|---------|
| Range | `.\tasks\plan-waves-multi.ps1 5-8` |
| List | `.\tasks\plan-waves-multi.ps1 5,6,7,8` |
| Include completed | `.\tasks\plan-waves-multi.ps1 5-8 -IncludeCompleted` |

Parameters: phase spec (positional, required: range `5-8`, list `5,6,7,8`, or mix `5-6,8`), `-IncludeCompleted`, `-BaseDir`, `-Output <path>`, `-Dbg`, `-SelfTest`. Exit: 0 clean, 1 blockers / cycle / residual conflicts (read the JSON), 2 usage error. Output `D:\datrix\.tmp\tasks\phases-05-08-waves.json`.

## `tasks\validate-dependencies.ps1`

Validate a phase's `dependencies.md` and task numbering.

| Form | Command |
|------|---------|
| Validate a phase | `.\tasks\validate-dependencies.ps1 -Phase 31` |
| Next free task number | `.\tasks\validate-dependencies.ps1 -Phase 31 -NextTaskNumber` |

Parameters: `-Phase <NN>` (position 0, required), `-NextTaskNumber`, `-BaseDir`, `-Output <path>`, `-Dbg`, `-SelfTest`. Exit: 0 PASS (with `-NextTaskNumber`, the number on stdout), 1 FAIL, 2 usage error. Output `D:\datrix\.tmp\tasks\phase-NN-validation.json`.

## `tasks\validate-task.ps1`

Validate task files against the tree as it is now (orientation block, `path:line` citations, size). Run it on every task a writer produces and before an orchestrator dispatches a wave.

| Form | Command |
|------|---------|
| A phase | `.\tasks\validate-task.ps1 -Phase 61` |
| Given tasks | `.\tasks\validate-task.ps1 -Task D:\datrix\<repo>\.tasks\phase-NN\task-NN-TT-<slug>.md` |
| Warnings fail | `.\tasks\validate-task.ps1 -Phase 61 -Strict` |
| Orientation required | `.\tasks\validate-task.ps1 -Phase 62 -RequireOrientation` |

Parameters: `-Task <file>[,<file>...]` (position 0), `-Phase <NN>` (position 1), `-Strict`, `-RequireOrientation`, `-BaseDir` (position 2), `-SelfTest`. Exit: 0 no errors (with `-Strict`, no warnings), 1 errors, 2 usage error.

## `tasks\retrofit-orientation.ps1`

Add an `## Orientation` block to tasks written before it existed (deterministic, no model). Dry run unless `-Apply`. Run `validate-task.ps1 -Phase <NN>` afterwards.

| Form | Command |
|------|---------|
| Dry run a phase | `.\tasks\retrofit-orientation.ps1 -Phase 61` |
| Apply | `.\tasks\retrofit-orientation.ps1 -Phase 61 -Apply` |
| Given tasks | `.\tasks\retrofit-orientation.ps1 -Task D:\datrix\<repo>\.tasks\phase-NN\task-NN-TT-<slug>.md` |

Parameters: `-Task <file>[,<file>...]` (position 0), `-Phase <NN>` (position 1), `-Apply`, `-BaseDir` (position 2), `-SelfTest`. Exit: 0 done, 2 usage error.

## `tasks\task-orientation-gate.ps1`

Behaviour checks for task orientation and citation validation.

| Form | Command |
|------|---------|
| Run the gate | `.\tasks\task-orientation-gate.ps1` |
| One area | `.\tasks\task-orientation-gate.ps1 -Only check_citations` |
| Harness self-test | `.\tasks\task-orientation-gate.ps1 -HarnessSelfTest` |
| Self-test | `.\tasks\task-orientation-gate.ps1 -SelfTest` |

Parameters: `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 all passed, 1 a check failed, 2 usage error.
