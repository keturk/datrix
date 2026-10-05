# Harness Guards

Read this when a hook refused something and you want the full picture of what fires where, or
before you add a check. You do not need it to work: every guard explains what to do in its own
message when it fires, so this table is no longer loaded into every turn.

## Enforced by the Harness

These are blocks, not suggestions — each fires whether or not you remember this file, and
each explains what to do in its own message. Every one fails **open**; none can wedge a
session. Do not route around a guard: if you are building a workaround for a block, you are
doing the wrong thing.

| Event | Hook | Refuses |
|---|---|---|
| `Stop` | `gate-orchestration-stop.py` | ending an armed `/task-orchestrator` run with tasks unresolved, on an offer to pause, or on a dodge/omission |
| `Stop` | `checklist.py` | ending a turn with a mechanical checklist item unsatisfied (`.claude/checklists/*.json`) |
| `Stop` | `gate-stop-exhaustion.py` | ending ANY turn on a context-exhaustion claim, a "remaining / still to fix / next up" handover section, a reported security downgrade (§13), or a reported expedient fix (§14) — inert when Jon asked you to stop or asked a question |
| `SubagentStop` | `check-agent-report.py` | a subagent report ending on a dodge without a B1–B4 proof or filed task, or reporting a security downgrade / expedient fix (neither is lifted by a proof; §13's one exception is B3) |
| `PreToolUse(Agent\|Task)` | `guard-no-nested-agents.py` | an `Agent`/`Task` call made from inside a subagent — depth is one; the orchestrating session may still dispatch |
| `PreToolUse(Bash\|PowerShell)` | `guard-predeploy-analysis.py` | a deploy with no fresh seam census in `.tmp/predeploy/` (dry-run/`--what-if` forms are always allowed) |
| `PreToolUse(Bash\|PowerShell)` | `guard-full-suite-runs.py` | every whole-suite run — bare/multi-package `test.ps1`, `-All`, `-Rerun`, tier sweeps, every `affected-gate.ps1` sweep — for every agent, main session included; no override, no ticket (`-ListTags` and `-SelfTest` run no test and are allowed). Also **sweeps assembled from targeting flags**: more than 3 `-Tag` values, or `-Keyword` across several packages |
| pytest collection | `datrix_common.testing.feature_tags` | a `-Tag`/`-Keyword` selection keeping more than 25% of a package's test tree (above 300 tests) — a full suite by instalments |
| `PreToolUse(Bash\|PowerShell)` | `guard-untargeted-scans.py` | whole-package `semgrep.ps1`/`libcst.ps1`/`ast-grep.ps1` runs with no `-Rule` and no `SCAN_QUESTION:` in the description; `-All` and subagent runs unconditionally |
| `PreToolUse(Bash\|PowerShell)` | `validate-script-invocation.py` | `generate.ps1` with `-All`/`-Domains`/`-TestSet` (no override) |
| `PreToolUse(Bash\|PowerShell)` | `guard-forbidden-commands.py` | git reverts, standalone type-checkers (`mypy` and equivalents, wrappers included), `pytest` invoked directly (use `test.ps1`), sleep-and-recheck polling loops inside one call (use `run_in_background`), and other prohibited commands. Sole exception: while Jon's `/resolve-conflicts` is the latest prompt, path-limited stash, index-only reset and `--ours/--theirs` pass |
| `PreToolUse(Bash\|PowerShell)` | `guard-shell-file-writes.py` | authoring file content from a shell — heredocs, `>`/`>>` into a file, `Set-Content`/`Out-File`, and `python -c`/`python - <<` bodies that write files |
| `PreToolUse(Bash\|PowerShell)` | `guard-repo-temp-dirs.py` | opening a temp/scratch dir inside a package repo from a shell — the `mkdir`, the redirect, and the `-Output*` argument |
| `PreToolUse(Write\|Edit\|NotebookEdit)` | `guard-repo-temp-dirs.py`, `guard-temp-file-policy.py` | temp/scratch dirs and files inside package repos |
| `PreToolUse(Write\|Edit\|NotebookEdit)` | `guard-repo-policy-edits.py` | a GitHub Actions workflow; marking a task COMPLETED by editing its heading instead of `complete.ps1`; writing into a `.tasks/phase-NN/` that does not exist (opening a phase) unless `/generate-tasks` or `/operationalize-design` is the recorded skill |
| `PreToolUse(Write\|Edit\|NotebookEdit)` | `guard-code-standards.py` | an edit that ADDS, to framework Python: a mock/`SimpleNamespace`/`mocker` to a test, an `except … : pass` handler, a `# TODO`/`FIXME` comment, a function or parameter without a type hint, `Any` (outside a `mode="before"` model validator), a pre-formatted log message (f-string, `.format()`, `%`, `+`), `.get(key, None)`, a function over cognitive complexity 15, or — in generator sources — entities flattened across services (`app.all_entities()`, one comprehension over every service's entities) (the delta only — existing code never blocks; unparseable → allowed) |
| `PreToolUse(Write\|Edit\|NotebookEdit)` | `guard-committed-content.py` | an edit that ADDS, to a file a framework repository commits, a design-doc or task-file reference (where `design-task-reference-gate.ps1` looks) or a registered customer term (anywhere git does not ignore) — the same detectors as the gates and the commit-time scan, on the delta only |
| `PreToolUse(Write\|Edit\|NotebookEdit)` | `gate-mandatory-reads.py` | any edit until the gated docs are read in this session (and re-read after a compaction) |
| `PreToolUse(Read)` | `redirect-large-read.py` | the **first** whole read (no `offset`/`limit`) of a large `.py` file or test log in the framework repos — answered with the file's code-index outline, or a local model's digest of the log; repeat the same Read to get the whole file (shown once per file per agent) |
| `PreToolUse(AskUserQuestion)` | `gate-decision-escalation.py` | handing a decision back to Jon mid-run instead of escalating |

`test-hook-config.py` compares this table with `settings.json` in both directions: a blocking
hook registered but missing here, or listed here but not registered, fails it.

## Adding a check

Put it in a hook or a test, not in CLAUDE.md. A rule written there is paid for on every turn and
competes with everything else in context; a rule in a hook is paid for only when it fires. If it
cannot be evaluated mechanically, it belongs in a read-when-needed doc. A check on the final reply
or on what the session ran needs no code: add a `.claude/checklists/*.json` item
(`.claude/hooks/checklist.py` lists the item types). Register a new hook in `settings.json` and add
its row above in the same change.
