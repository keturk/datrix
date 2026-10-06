# Quick Reference — Task Management Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## `tasks\todo.ps1`

Lists incomplete tasks (without `COMPLETED:` prefix) and incomplete bugs (without `FIXED:` prefix) from `.tasks/` and `.bugs/` folders across all projects.

| Mode | Command | Description |
|------|---------|-------------|
| **List all** | `.\tasks\todo.ps1` | All incomplete tasks and bugs |
| **Filter** | `.\tasks\todo.ps1 -Filter "parser"` | Filter by filename or title (case-insensitive) |
| **Custom base dir** | `.\tasks\todo.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Filter`, `-Dbg`

---

## `tasks\complete.ps1`

Marks a task markdown file as completed by updating its heading from `# Task ...` (or any status-prefixed variant) to `# COMPLETED: Task ...`.

| Mode | Command | Description |
|------|---------|-------------|
| **Mark complete (absolute path)** | `.\tasks\complete.ps1 "D:\datrix\datrix-common\.tasks\phase-05\task-05-01.md"` | Mark task complete with absolute path |
| **Mark complete (relative path)** | `.\tasks\complete.ps1 ".tasks\phase-05\task-05-01.md"` | Mark task complete with relative path |
| **Mark complete (filename only)** | `.\tasks\complete.ps1 "task-05-01.md"` | Searches all `.tasks/` folders for matching filename |
| **With debug** | `.\tasks\complete.ps1 "task-05-01.md" -Dbg` | Enable debug logging |

**Parameters:** `task_file` (required), `-Dbg`

**Note:** This script only marks the task heading as COMPLETED. You must manually add the `## How Solved` section with implementation details and proof-of-work.

---

## `tasks\completed.ps1`

Lists completed tasks (`COMPLETED:` prefix) and fixed bugs (`FIXED:` prefix) from `.tasks/` and `.bugs/` folders.

| Mode | Command | Description |
|------|---------|-------------|
| **List all** | `.\tasks\completed.ps1` | All completed tasks and fixed bugs |
| **Filter** | `.\tasks\completed.ps1 -Filter "parser"` | Filter by filename or title |
| **Custom base dir** | `.\tasks\completed.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Filter`, `-Dbg`

---

## `tasks\cleanup.ps1`

Lists/deletes task files from `.tasks/` folders. Optionally filters by phase number.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\tasks\cleanup.ps1` | Show all task files |
| **Delete all** | `.\tasks\cleanup.ps1 -Force` | Delete after confirmation |
| **Delete phases < N** | `.\tasks\cleanup.ps1 -Force -Phase 60` | Delete only phases before 60 |

**Parameters:** `-BaseDir`, `-Force`, `-Phase` (delete phases < N), `-Dbg`

---

## `tasks\latest-phase.ps1`

Returns the highest phase number found in `.tasks/` folders. Outputs only the number (for scripting).

| Mode | Command | Description |
|------|---------|-------------|
| **Get latest** | `.\tasks\latest-phase.ps1` | Outputs phase number only |
| **With debug** | `.\tasks\latest-phase.ps1 -Dbg` | Shows all found phases |
| **Custom base dir** | `.\tasks\latest-phase.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Dbg`

---

## Phase-Analysis Scripts (agent-oriented: minimal console, details to JSON under `D:\datrix\.tmp\tasks\`)

These parse a phase's task files across ALL repos so AI agents (orchestrators, executors, verifiers) read one compact JSON instead of N task files. Each prints a 1-2 line summary plus a `Details:` path.

## `tasks\phase-status.ps1`

Full metadata snapshot of a phase: per task — `task_id`, `task_path`, `title`, `status`/`is_completed`, `package`, `category`, `depends_on` (normalized), `design_reference`, `design_acceptance_property` (full text), `files_to_review`, `files_to_create_modify`, `targeted_tests`, `languages`, `has_how_solved`, `how_solved_redflags` (BLOCKED/partial/workaround/... markers) — plus phase-level `dependencies_md` format (json/legacy/absent), `provenance`, `dep_mismatches`, and `missing_dependency_files`. Reports live disk truth; re-run after any task-file change.

| Mode | Command | Description |
|------|---------|-------------|
| **Snapshot a phase** | `.\tasks\phase-status.ps1 31` | All repos' phase-31 tasks → `D:\datrix\.tmp\tasks\phase-31-status.json` |
| **Custom base dir** | `.\tasks\phase-status.ps1 31 -BaseDir D:\other` | Different workspace |

**Parameters:** phase number (positional, required), `-BaseDir`, `-Output <path>` (override the default JSON path), `-Dbg`. **Exit codes:** 0 = done, 2 = usage / phase not found.

## `tasks\plan-waves.ps1`

Computes the execution plan for a phase: Kahn topological waves over the dependency graph (completed deps count as satisfied), file-conflict splitting into sequential sub-waves, Quality-Gate-last / Verification-after-deps ordering, `cycle` detection, `blocking_issues[]` (`MISSING_DEP_FILE`, `UNMET_CROSS_PHASE_DEP`, `MIXED_LANGUAGE_TASK`, `DEP_MISMATCH`), and `can_parallelize`.

| Mode | Command | Description |
|------|---------|-------------|
| **Plan pending tasks** | `.\tasks\plan-waves.ps1 31` | Waves for non-completed tasks → `D:\datrix\.tmp\tasks\phase-31-waves.json` |
| **Include completed** | `.\tasks\plan-waves.ps1 31 -IncludeCompleted` | Full-phase wave structure (audit/compare use) |
| **Custom base dir** | `.\tasks\plan-waves.ps1 31 -BaseDir D:\other` | Different workspace |

**Parameters:** phase number (positional, required), `-IncludeCompleted`, `-BaseDir`, `-Output <path>`, `-Dbg`. **Exit codes:** 0 = plan clean, 1 = blockers/cycle present (read the JSON), 2 = usage error.

## `tasks\plan-waves-multi.ps1`

Same plan, but over SEVERAL phases run as one batch. Use it when phases are executed together rather than one after another: a dependency into another batched phase becomes an ordinary graph edge instead of an `UNMET_CROSS_PHASE_DEP` blocker, so the batch collapses to its real dependency depth instead of the sum of the per-phase plans.

Batching also hides a conflict `plan-waves.ps1` cannot see — it plans one phase, so two tasks in DIFFERENT phases writing the same file are invisible to its wave splitter, and nothing stops the later phase's task from being scheduled first. This script closes that: it adds the minimum dependency edges needed to stop a later phase's task running at or before an earlier phase's task on a shared file (reported as `implicit_order_edges`, never silent), then asserts as a post-condition that no wave contains two writers of one file (`residual_file_conflicts`, which must be empty).

| Mode | Command | Description |
|------|---------|-------------|
| **Plan a phase range** | `.\tasks\plan-waves-multi.ps1 5-8` | Phases 5,6,7,8 as one batch → `D:\datrix\.tmp\tasks\phases-05-08-waves.json` |
| **Plan a phase list** | `.\tasks\plan-waves-multi.ps1 5,6,7,8` | Same, comma form (mixes allowed: `5-6,8`) |
| **Include completed** | `.\tasks\plan-waves-multi.ps1 5-8 -IncludeCompleted` | Full batch wave structure (audit/compare use) |

**Parameters:** phase spec (positional, required — range `5-8`, list `5,6,7,8`, or mix `5-6,8`; at least two phases), `-IncludeCompleted`, `-BaseDir`, `-Output <path>`, `-Dbg`. **Exit codes:** 0 = plan clean, 1 = blockers/cycle/residual conflicts present (read the JSON), 2 = usage error.

**Output fields beyond `plan-waves.ps1`'s:** `phases`, `implicit_order_edges` (each with the task pair, the shared file, and why the edge was added), `order_repair_passes`, `residual_file_conflicts` (must be empty), and a `phases` list on every `wave_details` entry.

**Note:** a dependency on a phase OUTSIDE the batch is still held to the original rule — it must exist and be COMPLETED, since nothing in the batch will produce it. Single phase → use `plan-waves.ps1`; this script rejects a spec selecting fewer than two.

## `tasks\validate-dependencies.ps1`

Validates a phase's `dependencies.md` + task numbering: valid Step-7 JSON (legacy "Group N" format → WARN) covering ALL discovered task files, every dependency resolves, graph acyclic, each task file's `**Depends on:**` matches its JSON entry exactly, `task_path`s absolute + existing, task numbers unique and sequential across repos, provenance stamp present (INFO). `-NextTaskNumber` mode prints ONLY the next free two-digit task number for the phase (for `/generate-tasks` and readiness audits).

| Mode | Command | Description |
|------|---------|-------------|
| **Validate a phase** | `.\tasks\validate-dependencies.ps1 -Phase 31` | PASS/FAIL + violations → `D:\datrix\.tmp\tasks\phase-31-validation.json` |
| **Next free task number** | `.\tasks\validate-dependencies.ps1 -Phase 31 -NextTaskNumber` | Prints only the number (e.g. `18`) |
| **Custom base dir** | `.\tasks\validate-dependencies.ps1 -Phase 31 -BaseDir D:\other` | Different workspace |

**Parameters:** `-Phase <NN>` (required), `-NextTaskNumber`, `-BaseDir`, `-Output <path>`, `-Dbg`. **Exit codes:** validate mode 0 = PASS / 1 = FAIL / 2 = usage; `-NextTaskNumber` 0 with the number on stdout.

## `tasks\retrofit-orientation.ps1`

Gives tasks written **before** the `## Orientation` block existed one — deterministically, with no writer and no model. A Python file in a task's "Files to Review Before Starting" that the task does not edit becomes an exact `outline:` entry (definitions with line ranges plus the module summary), and its line leaves the list so the agent is no longer told to read it whole; a function a citation names whose definition is unique in the tree, in a file the task does not edit, becomes a `symbol:` entry. It does **not** write `refs:` or `explain:`: which callers matter and which question to ask about a test's style are a writer's judgment.

Left alone: quality-gate tasks (reading the code is the job), tasks that already have a block (so it is idempotent), tasks with no review list or nothing the index can answer. A task is written only if the rewrite parses, every entry in it resolves, and the task's scope fields (`Depends on`, design reference and acceptance property, files to create/modify, targeted tests) read back unchanged. Dry run unless `-Apply`; `-Apply` first copies each original to `D:\datrix\.tmp\retrofit-orientation\<stamp>\`.

| Mode | Command | Description |
|------|---------|-------------|
| **Dry run a phase** | `.\tasks\retrofit-orientation.ps1 -Phase 61` | Per task: entries it would add, review lines it would remove, KB of source the agent was told to read vs KB answered |
| **Apply** | `.\tasks\retrofit-orientation.ps1 -Phase 61 -Apply` | Writes the rewritten tasks (originals copied aside first) |
| **Given tasks** | `.\tasks\retrofit-orientation.ps1 -Task D:\datrix\<repo>\.tasks\phase-NN\task-NN-TT-<slug>.md` | One or more task files |

**Parameters:** `-Task <file>[,<file>...]`, `-Phase <NN>`, `-Apply`, `-BaseDir`. **Exit codes:** 0 = done, 2 = usage error. Run `validate-task.ps1 -Phase <NN>` afterwards.

## `tasks\validate-task.ps1`

Validates task files **against the tree as it is now**, deterministically and without a model. Run it on every task a writer produces, and again before an orchestrator dispatches a wave: a phase runs for days while other tasks change the same files, so a citation or an orientation entry written against last week's tree goes stale.

- **Orientation** — the task's `## Orientation` block (see `agent-templates/task-implementation-agent.md`, "Orientation") parses, and every entry resolves: a `symbol` or `refs` the code index finds, an `outline` of a file that exists, an `explain` over files a local model may read (framework repos and test output). A question that asks *where something is defined* or *who calls it* is an error: a model invents those answers, and `symbol` / `refs` answer them exactly.
- **Citations** — every `path:line` / `path:first-last` in the task's prose (never inside a code fence): ERROR when the file does not exist (unless the task creates it) or the lines are past its end; WARN when an identifier quoted on the same line is no longer within three lines of the cited range (the lines have moved). Paths with `...` and bare file names that are not unique in the task's repository are skipped, never guessed.
- **Size** — the implementer reads the whole task before its first edit. ERROR when a task that is not COMPLETED exceeds 1500 lines (split it: one task per language or file group; replace code bodies with contracts); WARN above 600 lines; WARN when `## Implementation Notes` and `## How Solved` together exceed 60 lines. A COMPLETED task is exempt from the length limit.

| Mode | Command | Description |
|------|---------|-------------|
| **A phase** | `.\tasks\validate-task.ps1 -Phase 61` | Every task of the phase in every repo; exit 1 on any error |
| **Given tasks** | `.\tasks\validate-task.ps1 -Task D:\datrix\<repo>\.tasks\phase-NN\task-NN-TT-<slug>.md` | One or more task files |
| **Warnings fail** | `.\tasks\validate-task.ps1 -Phase 61 -Strict` | A moved line fails the run |
| **Orientation required** | `.\tasks\validate-task.ps1 -Phase 62 -RequireOrientation` | A task with no `## Orientation` is an error (for tasks written to the new template) |

**Parameters:** `-Task <file>[,<file>...]`, `-Phase <NN>`, `-Strict`, `-RequireOrientation`, `-BaseDir`. **Exit codes:** 0 = no errors (and, with `-Strict`, no warnings), 1 = errors, 2 = usage error.

---

## `tasks\task-orientation-gate.ps1`

Behaviour checks for task orientation and citation validation (`common/lib/datrix_scripts/task_orientation.py`, `tasks/lib/task_citations.py`, `tasks/lib/validate_task.py`, wrapped by `tasks\validate-task.ps1`). Each check builds a real workspace in a temporary directory (framework repositories with real Python, task files under `.tasks/phase-NN`) and runs the real code index over it; explanations are answered by a real model server on loopback, never the network's. The checks cover:

- the `## Orientation` block read by the one task parser (`parse_task_file`), and prose lines that exclude code fences
- every malformed entry rejected with what to write instead; every question that asks where something is defined or who calls it rejected (a local model invents those answers; `symbol` / `refs` answer them exactly)
- the resolver: facts exact from the index, a stale entry called out as a stale premise, an explanation marked as a lead, no model server leaving the facts intact
- the citation checker: missing file / line past the end / backwards range are errors; an abbreviated path, a relative path or bare file name that several repositories carry, and a file another task of the phase creates are not errors; a name written beside a citation that is nowhere near its lines is a warning; names elsewhere in the sentence, language names and code fences are ignored
- the validator end to end (`--phase`, `--require-orientation`) and its exit codes

It is a repo-level validation **script**, not a pytest suite.

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\tasks\task-orientation-gate.ps1` | Run every check |
| **One area** | `.\tasks\task-orientation-gate.ps1 -Only check_citations` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\tasks\task-orientation-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.
