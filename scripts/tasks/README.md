# Task Management Scripts

Scripts over the task and bug files tracked in `.tasks/` and `.bugs/` folders within each project. The
commands, parameters and exit codes of each script are in [quick-reference.md](quick-reference.md); this
file holds what they check and how they are built.

Every script is a wrapper rendered from `common/templates/entrypoint.ps1` around a Python module in
`common/lib/datrix_scripts/tasks/` (named under each section), run in the shared venv. Each has a POSIX
twin `tasks\<name>.sh` that takes the module's own flags, each parameter as `--kebab-name`
(`bash tasks/todo.sh --filter parser`). Options are spelled in full: an abbreviation is a usage error
(exit 2), never expanded. `-SelfTest` runs the module's checks over a planted workspace in a temporary
directory, then the wrapper seam checks; it never reads the real `.tasks` folders.

## Task/Bug System

**Task format:** the title line `# Task 123: Implement feature X`, then the description. When completed,
the title is prefixed with `COMPLETED:` (`# COMPLETED: Task 123: Implement feature X`) — through
`complete.ps1`, never by hand.

**Bug format:** the title line `# Bug 456: Fix crash on startup`, then the description. When fixed, the
title is prefixed with `FIXED:` (`# FIXED: Bug 456: Fix crash on startup`).

## `todo.ps1`

Lists incomplete tasks (without `COMPLETED:` prefix) and incomplete bugs (without `FIXED:` prefix) from
`.tasks/` and `.bugs/` folders across all projects.

Module: `datrix_scripts.tasks.todo` (the scan it shares with `completed.ps1` in
`datrix_scripts.tasks.task_listing`). The filter matches the file name or title as a substring,
case-insensitively, with `*` and `?` as wildcards.

## `complete.ps1`

Marks a task markdown file as completed by updating its heading from `# Task ...` (or any
status-prefixed variant) to `# COMPLETED: Task ...`. The reference may be an absolute path, a relative
path, or a file name (every `.tasks/` folder is searched for it).

Module: `datrix_scripts.tasks.complete`. It refuses (exit 1, file untouched) a reference that matches no
file or several, and a file whose first heading is not a task title.

This script only marks the task heading as COMPLETED. You must manually add the `## How Solved` section
with implementation details and proof-of-work.

## `completed.ps1`

Lists completed tasks (`COMPLETED:` prefix) and fixed bugs (`FIXED:` prefix) from `.tasks/` and `.bugs/`
folders.

Module: `datrix_scripts.tasks.completed` (the scan it shares with `todo.ps1` in
`datrix_scripts.tasks.task_listing`).

## `cleanup.ps1`

Lists/deletes task artifacts (files named `task-*` or `dependencies.md`, at any depth) from `.tasks/`
folders, then removes the folders they leave empty. Optionally filters by phase number (`-Phase N`
deletes only phases before N). Nothing is deleted without `-Force` and a typed `yes`; an end of input
answers no. No symbolic link or junction is entered.

Module: `datrix_scripts.tasks.cleanup` (the confirmation and folder removal in
`datrix_scripts.cleanup_utils`).

## `latest-phase.ps1`

Returns the highest phase number found in `.tasks/` folders. Outputs only the number (for scripting).
`-Dbg` shows all found phases.

Module: `datrix_scripts.tasks.latest_phase`. With no phase folder it prints nothing (with `-Dbg`, a line
saying so).

## Phase-analysis scripts

Agent-oriented: minimal console, details to JSON under `D:\datrix\.tmp\tasks\`. These parse a phase's
task files across ALL repos so AI agents (orchestrators, executors, verifiers) read one compact JSON
instead of N task files. Each prints a 1-2 line summary plus a `Details:` path.

### `phase-status.ps1`

Full metadata snapshot of a phase: per task — `task_id`, `task_path`, `title`, `status`/`is_completed`,
`package`, `category`, `depends_on` (normalized), `design_reference`, `design_acceptance_property` (full
text), `files_to_review`, `files_to_create_modify`, `targeted_tests`, `languages`, `has_how_solved`,
`how_solved_redflags` (BLOCKED/partial/workaround/... markers) — plus phase-level `dependencies_md`
format (json/legacy/absent), `provenance`, `dep_mismatches`, and `missing_dependency_files`. Reports
live disk truth; re-run after any task-file change.

Module: `datrix_scripts.tasks.phase_status`.

### `plan-waves.ps1`

Computes the execution plan for a phase: Kahn topological waves over the dependency graph (completed
deps count as satisfied), file-conflict splitting into sequential sub-waves, Quality-Gate-last /
Verification-after-deps ordering, `cycle` detection, `blocking_issues[]` (`MISSING_DEP_FILE`,
`UNMET_CROSS_PHASE_DEP`, `MIXED_LANGUAGE_TASK`, `DEP_MISMATCH`), and `can_parallelize`.
`-IncludeCompleted` gives the full-phase wave structure (audit/compare use).

Module: `datrix_scripts.tasks.plan_waves`.

### `plan-waves-multi.ps1`

Same plan, but over SEVERAL phases run as one batch. Use it when phases are executed together rather
than one after another: a dependency into another batched phase becomes an ordinary graph edge instead
of an `UNMET_CROSS_PHASE_DEP` blocker, so the batch collapses to its real dependency depth instead of
the sum of the per-phase plans.

Batching also hides a conflict `plan-waves.ps1` cannot see — it plans one phase, so two tasks in
DIFFERENT phases writing the same file are invisible to its wave splitter, and nothing stops the later
phase's task from being scheduled first. This script closes that: it adds the minimum dependency edges
needed to stop a later phase's task running at or before an earlier phase's task on a shared file
(reported as `implicit_order_edges`, never silent), then asserts as a post-condition that no wave
contains two writers of one file (`residual_file_conflicts`, which must be empty).

Output fields beyond `plan-waves.ps1`'s: `phases`, `implicit_order_edges` (each with the task pair, the
shared file, and why the edge was added), `order_repair_passes`, `residual_file_conflicts` (must be
empty), and a `phases` list on every `wave_details` entry.

A dependency on a phase OUTSIDE the batch is still held to the original rule — it must exist and be
COMPLETED, since nothing in the batch will produce it. Single phase → use `plan-waves.ps1`; this script
rejects a spec selecting fewer than two.

Module: `datrix_scripts.tasks.plan_waves_multi`.

### `validate-dependencies.ps1`

Validates a phase's `dependencies.md` + task numbering: valid Step-7 JSON (legacy "Group N" format →
WARN) covering ALL discovered task files, every dependency resolves, graph acyclic, each task file's
`**Depends on:**` matches its JSON entry exactly, `task_path`s absolute + existing, task numbers unique
and sequential across repos, provenance stamp present (INFO). `-NextTaskNumber` mode prints ONLY the next
free two-digit task number for the phase (for `/generate-tasks` and readiness audits).

Module: `datrix_scripts.tasks.validate_dependencies`.

### `retrofit-orientation.ps1`

Gives tasks written **before** the `## Orientation` block existed one — deterministically, with no
writer and no model. A Python file in a task's "Files to Review Before Starting" that the task does not
edit becomes an exact `outline:` entry (definitions with line ranges plus the module summary), and its
line leaves the list so the agent is no longer told to read it whole; a function a citation names whose
definition is unique in the tree, in a file the task does not edit, becomes a `symbol:` entry. It does
**not** write `refs:` or `explain:`: which callers matter and which question to ask about a test's style
are a writer's judgment.

Left alone: quality-gate tasks (reading the code is the job), tasks that already have a block (so it is
idempotent), tasks with no review list or nothing the index can answer. A task is written only if the
rewrite parses, every entry in it resolves, and the task's scope fields (`Depends on`, design reference
and acceptance property, files to create/modify, targeted tests) read back unchanged. Dry run unless
`-Apply`; the dry run reports, per task, the entries it would add, the review lines it would remove, and
the KB of source the agent was told to read against the KB answered. `-Apply` first copies each original
to `D:\datrix\.tmp\retrofit-orientation\<stamp>\`.

Module: `datrix_scripts.tasks.retrofit_orientation`.

### `validate-task.ps1`

Validates task files **against the tree as it is now**, deterministically and without a model. Run it on
every task a writer produces, and again before an orchestrator dispatches a wave: a phase runs for days
while other tasks change the same files, so a citation or an orientation entry written against last
week's tree goes stale.

- **Orientation** — the task's `## Orientation` block (see `.claude/skills/generate-tasks/SKILL.md`,
  "Orientation (the `## Orientation` block)") parses, and every entry resolves: a `symbol` or `refs` the
  code index finds, an `outline` of a file that exists, an `explain` over files a local model may read
  (framework repos and test output). A question that asks *where something is defined* or *who calls it*
  is an error: a model invents those answers, and `symbol` / `refs` answer them exactly.
- **Citations** — every `path:line` / `path:first-last` in the task's prose (never inside a code fence):
  ERROR when the file does not exist (unless the task creates it) or the lines are past its end; WARN
  when an identifier quoted on the same line is no longer within three lines of the cited range (the
  lines have moved). Paths with `...` and bare file names that are not unique in the task's repository
  are skipped, never guessed.
- **Size** — the implementer reads the whole task before its first edit. ERROR when a task that is not
  COMPLETED exceeds 1500 lines (split it: one task per language or file group; replace code bodies with
  contracts); WARN above 600 lines; WARN when `## Implementation Notes` and `## How Solved` together
  exceed 60 lines. A COMPLETED task is exempt from the length limit.

Module: `datrix_scripts.tasks.validate_task` (the citation checker in `datrix_scripts.tasks.task_citations`).

## `task-orientation-gate.ps1`

Behaviour checks for task orientation and citation validation
(`common/lib/datrix_scripts/task_orientation.py`, `datrix_scripts.tasks.task_citations`,
`datrix_scripts.tasks.validate_task`, wrapped by `tasks\validate-task.ps1`). Each check builds a real
workspace in a temporary directory (framework repositories with real Python, task files under
`.tasks/phase-NN`) and runs the real code index over it; explanations are answered by a real model
server on loopback, never the network's. The checks cover:

- the `## Orientation` block read by the one task parser (`parse_task_file`), and prose lines that exclude code fences
- every malformed entry rejected with what to write instead; every question that asks where something is defined or who calls it rejected (a local model invents those answers; `symbol` / `refs` answer them exactly)
- the resolver: facts exact from the index, a stale entry called out as a stale premise, an explanation marked as a lead, no model server leaving the facts intact
- the citation checker: missing file / line past the end / backwards range are errors; an abbreviated path, a relative path or bare file name that several repositories carry, and a file another task of the phase creates are not errors; a name written beside a citation that is nowhere near its lines is a warning; names elsewhere in the sentence, language names and code fences are ignored
- the validator end to end (`--phase`, `--require-orientation`) and its exit codes

It is a repo-level validation **script**, not a pytest suite.

Module: `datrix_scripts.tasks.task_orientation_gate`.
