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
