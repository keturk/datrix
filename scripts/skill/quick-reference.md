# Skill Scripts Quick Reference

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each command produces, how the chains decide, the model choices: [README.md](README.md).

Scripts for the agent skills under `.claude/skills/`. Each has a POSIX twin `.sh` taking the same options as `--kebab` flags.

## `skill\implement-design.ps1` and `skill\skill-chain.ps1`

Run skills one after another as headless `claude -p` steps, each on its own skill's model and effort. `implement-design.ps1` runs plan → implement units → verify → absorb for one design; `skill-chain.ps1` runs any prompts in order and stops at the first error.

| Form | Command |
|------|---------|
| Implement a design | `.\skill\implement-design.ps1 -Design "D:\datrix\design\<file>.md"` |
| Every design of `D:\datrix\design` | `.\skill\implement-design.ps1 -All` |
| Every design of another folder | `.\skill\implement-design.ps1 -All "D:\datrix\design\<folder>"` |
| Resume at a step | `.\skill\implement-design.ps1 -Design "<file>" -StartAt verify` |
| Any sequence | `.\skill\skill-chain.ps1 "/fix-codegen-python <index.json>" "/commit-and-push"` |
| One session throughout | add `-Resume` |
| Preview the steps | add `-DryRun` |
| Summary lines only | add `-Quiet` |

Parameters: `-Design` (or first positional; a folder with `-All`), `-Count` (default 10 designs of `D:\datrix\design` when no `-Design`), `-All` (every design of the folder, no count cap; refused with `-Count`, a file, or `-StartAt`; the first design that does not finish stops the run), `-StartAt` (`implement`, `verify`, `absorb`), `-KeepSource`, `-MaxRounds` (default 3) for `implement-design.ps1`; the prompts as positionals for `skill-chain.ps1`. Both: `-Resume`, `-PermissionMode auto|acceptEdits|dontAsk|bypassPermissions` (default `auto`), `-MaxBudgetUsd` (per step), `-DryRun`, `-Quiet`. Before each unit session `implement-design.ps1` loads every registered plugin in a fresh interpreter and stops with 1 when one fails to load, printing the error's end; rerun once it loads. It reads a ledger unit only as a markdown table row (id first, state `[ ]`/`[x]` last) and stops with 1 on a ledger holding no such row. The ledger is bounded (24,000 bytes; cell, state and line lengths; only `## Units` and `## Decisions`): a unit session that starts on an over-limit ledger is told to shrink it, and the chain stops with 1 when it stays over. The files a unit changed are listed in its proof file under `## Files changed`; the script gathers them into `implement-direct-<design>-files.md` for verify. Logs: `D:\datrix\.tmp\skill-chain\<timestamp>\`. Exit: 0 done, 1 a step errored or a check failed, 2 a step stopped for a decision only Jon can make (its reply and session id are printed).

From Git Bash set `MSYS_NO_PATHCONV=1` for `skill-chain.ps1`, or a leading `/` in a prompt becomes a Windows path.

## `skill\implement-finding.ps1`

Drain the findings inbox one finding at a time: one fresh headless `/implement-finding` session per finding.

| Form | Command |
|------|---------|
| First 10 findings | `.\skill\implement-finding.ps1` |
| Fewer | `.\skill\implement-finding.ps1 -Count 3` |
| One folder | `.\skill\implement-finding.ps1 azure` |
| Every finding of the inbox | `.\skill\implement-finding.ps1 -All` |
| Every finding of one folder | `.\skill\implement-finding.ps1 -All D:\datrix\findings\azure` |
| Given files | `.\skill\implement-finding.ps1 -Finding "D:\datrix\findings\<file>.md"` |
| Preview | add `-DryRun` |

Parameters: `-Count` (default 10), `-All` (every finding of `-Dir`, or of every inbox folder in turn, no count cap; refused with `-Count` or `-Finding`), `-Finding`, `-Dir` (absolute, or relative to `findings`; default the subfolders in turn), `-Model` (default `claude-opus-5-5`), `-Effort` (default `high`), `-PermissionMode`, `-MaxBudgetUsd`, `-DryRun`, `-Quiet`. Exit: 0 every finding deleted, 1 a session erred or a finding was left in place, 2 a session stopped for a decision only Jon can make.

## `skill\organize-findings.ps1`

Sort findings files lying directly in the findings folder into one level of area subfolders, by file name. Run by `/organize-findings`.

| Form | Command |
|------|---------|
| Sort the inbox | `.\skill\organize-findings.ps1` |
| Preview | `.\skill\organize-findings.ps1 -DryRun` |
| Names only (no model) | `.\skill\organize-findings.ps1 -NoModel` |
| Another folder | `.\skill\organize-findings.ps1 -Dir "<folder>"` |

Parameters: `-Dir` (default `<workspace>\findings`), `-DryRun`, `-NoModel`, `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (seconds, default 300), `-SelfTest`. Exit: 0 all sorted, 1 folder unreadable or a move failed, 2 some files stayed, 3 a model was needed and none answered.

## `skill\skill-assist.ps1`

The mechanical phases of agent skills, done by a script or a local model. Each command writes to `d:\datrix\.tmp\assist\` and prints the path with a one-line summary; a local model's output is a lead, the skill keeps every verdict. Run `.\skill\skill-assist.ps1 <command> <arguments>`.

| Command | Skill phase it serves |
|---------|-----------------------|
| `context-digest --phase N` | `/task-orchestrator` shared-context pre-read |
| `readiness --phase N [--no-model]` | `/task-orchestrator` 1e readiness audit |
| `findings-index [--dir D]` | `/merge-findings` Phase 1; `/delete-redundant-findings` Phase 1 |
| `findings-check --delete F... [--dir D] [--keep-raw]` | `/merge-findings` and `/delete-redundant-findings` Phase 4 (with `--keep-raw`) |
| `findings-redundant [--dir D] [--no-model]` | `/delete-redundant-findings` Phase 1 |
| `findings-redundant-delete [--plan P] [--dir D]` | `/delete-redundant-findings` Phase 4 |
| `finding-select [--count N] [--dir D]` | `/implement-finding` selection |
| `finding-close --finding F [--session-log L]` | `/implement-finding`, `implement-finding.ps1` delete |
| `checklist --design PATH` | `/verify-implementation` Phase 1 |
| `absorb-transfer --design PATH --target T...` | `/absorb-design` Phase 3 |
| `absorb-references --design PATH [--also P...]` | `/absorb-design` Phase 4 |
| `absorb-delete --design PATH [--verified V \| --knowledge-only] [--also P...]` | `/absorb-design` Phase 4 delete |
| `bug-resolution --report R --repo P... [--file F...] ...` | `/fix-bug-report` Phase 3 |
| `design-inventory [--dir D] [--design-dir DD]` | `/consolidate-to-design` Phase 1 |
| `design-verify [--dir D] [--no-model]` | `/consolidate-to-design` Phase 1 |
| `design-plan [--dir D] [--design-dir DD] [--no-model]` | `/consolidate-to-design` Phase 2 |
| `design-xref [--design-dir DD]` | `/verify-design` Phase 1; `/consolidate-to-design` Phase 6 |
| `rule-names --site PATH:LINE... [--sites-file F] [--apply]` | implementing a design that refuses unnamed `validate` rules (`DBO008`) |
| `design-check [--design-dir DD]` | `/consolidate-to-design` Phase 6; `/verify-design` Phase 1 |
| `design-close --finding F... [--fixed ID...] [--dir D] [--design-dir DD] [--apply]` | `/consolidate-to-design` Phase 6 |

Parameters: the command, then its own python-style arguments; the model commands also take `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (seconds, default 600). `--no-model` skips the model where listed. Exit: 0 done, 1 the request could not be carried out, 2 the check found something to act on (`findings-check` FAIL, `finding-close` or `absorb-delete` kept the target, `absorb-transfer` partial/missing, `absorb-references` found lines, `design-check` or `design-xref` errors), 3 no local model answered — do that phase yourself. What each command produces and checks: [README.md](README.md#skill-assistps1).

## `skill\skill-assist-gate.ps1`

Checks every assist module and the `skill-assist.ps1` command line against real files and a stand-in model server. Run it after changing an assist module.

| Form | Command |
|------|---------|
| Run every check | `.\skill\skill-assist-gate.ps1` |
| One check | `.\skill\skill-assist-gate.ps1 -Only <check name>` |
| Prove the harness fails a broken check | `.\skill\skill-assist-gate.ps1 -HarnessSelfTest` |
| Self-test | `.\skill\skill-assist-gate.ps1 -SelfTest` |

Parameters: `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 all passed, 1 a check failed.
