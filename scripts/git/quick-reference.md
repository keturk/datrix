# Quick Reference — Git Scripts

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each script does, the pre-commit checks, how messages are generated: [README.md](README.md).

Every script takes `-SelfTest` and has a POSIX twin `git/<name>.sh` taking the same options as `--kebab` flags. No script here runs `git stash`, `reset`, `checkout`, `restore` or `revert`.

## `git\status.ps1`

Git status of every repository under the workspace root.

| Form | Command |
|------|---------|
| Summary | `.\git\status.ps1` |
| Detailed | `.\git\status.ps1 -Detailed` |

Parameters: `-Detailed`, `-Dbg`, `-SelfTest`

## `git\pull.ps1`

Pull every repository, then summarize by outcome (Updated, Up to date, Conflict, Blocked by local changes, Failed). A repo left Conflict or Blocked is handed to a Claude agent running `/resolve-conflicts <repo>`, then pulled again.

| Form | Command |
|------|---------|
| Pull all | `.\git\pull.ps1` |
| Report only, no agent | `.\git\pull.ps1 -ConflictRepairAttempts 0` |

Parameters: `-ConflictRepairAttempts` (default 2; 0 = report only), `-ConflictRepairModel`, `-ConflictRepairEffort`, `-ConflictRepairTimeoutMs` (default 3600000), `-SelfTest`. Exit: 0 every repo updated or up to date, 1 a repo conflicted / was blocked / failed, 2 could not start.

## `git\fix-line-endings.ps1`

Give each modified file the line endings of its index copy (content untouched).

| Form | Command |
|------|---------|
| Preview | `.\git\fix-line-endings.ps1 -DryRun` |
| One repo | `.\git\fix-line-endings.ps1 -Repo datrix-codegen-python` |
| Every framework repo | `.\git\fix-line-endings.ps1` |

Parameters: `-Repo <name,...>`, `-DryRun`, `-SelfTest`. Exit: 0 done or clean dry run, 2 a git command failed or bad argument.

## `git\resolve-pull.ps1`

Pull repositories over uncommitted local work (the mechanical half of `/resolve-conflicts`). Agents may run it only after Jon typed `/resolve-conflicts` in the session.

| Form | Command |
|------|---------|
| Pull over local work | `.\git\resolve-pull.ps1 datrix-common datrix-cli` |
| Finish a hand merge | `.\git\resolve-pull.ps1 datrix-common -Finish` |
| Finish, a line merged on purpose | `.\git\resolve-pull.ps1 datrix-common -Finish -Merged docs/a.md` |

Parameters: `-Repo` (positional; none = every git repository), `-Finish`, `-Merged <path,...>`, `-NoModel`, `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (default 300), `-SelfTest`. Outcomes per repo: `up to date`, `finished`, `nothing to finish`, `NEEDS HAND MERGE`, `UNFINISHED`, `CONFLICT ALREADY IN PROGRESS`, `FAILED`. Exit: 0 all up to date or finished, 1 a repo needs a hand merge / has a conflict / failed, 2 could not start.

## `git\pre-review.ps1`

First-pass review of the lines pending changes add to Python files; run before `commit-and-push.ps1`. Definite rules: `get-none`, `bare-except`, `except-pass`, `todo-comment`, `untyped-def`, `placeholder`, `syntax-error`.

| Form | Command |
|------|---------|
| Review | `.\git\pre-review.ps1` |
| Plus advisory local-model findings | `.\git\pre-review.ps1 -ModelReview` |

Parameters: `-ModelReview`, `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (default 180), `-SelfTest`. Exit: 0 no definite findings, 1 findings (`file:line rule: explanation`), 2 could not run.

## `git\pre-review-gate.ps1`

Behaviour checks for the pre-review.

| Form | Command |
|------|---------|
| Run the gate | `.\git\pre-review-gate.ps1` |
| One area | `.\git\pre-review-gate.ps1 -Only check_model` |
| Harness self-test | `.\git\pre-review-gate.ps1 -HarnessSelfTest` |
| Self-test | `.\git\pre-review-gate.ps1 -SelfTest` |

Parameters: `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 all passed, 1 a check failed, 2 usage error.

## `git\resolve-pull-gate.ps1`

Behaviour checks for `resolve-pull.ps1` over a temporary origin and clone.

| Form | Command |
|------|---------|
| Run the gate | `.\git\resolve-pull-gate.ps1` |
| One area | `.\git\resolve-pull-gate.ps1 -Only check_conflict` |
| Harness self-test | `.\git\resolve-pull-gate.ps1 -HarnessSelfTest` |
| Self-test | `.\git\resolve-pull-gate.ps1 -SelfTest` |

Parameters: `-Only`, `-HarnessSelfTest`, `-SelfTest`, `-Dbg`. Exit: 0 all passed, 1 a check failed, 2 usage error.

## `git\commit-and-push.ps1`

Commit and push every dirty repo in one pass: pre-commit checks across all repos first, then themed change sets, one message per set, one push per repo. Stops on the first git failure.

| Form | Command |
|------|---------|
| Auto (first local model that answers, else Claude) | `.\git\commit-and-push.ps1` |
| Require a local model | `.\git\commit-and-push.ps1 -MessageSource local` |
| Use the Claude Code CLI | `.\git\commit-and-push.ps1 -MessageSource claude` |
| Preview messages, commit nothing | `.\git\commit-and-push.ps1 -DryRun` |

Parameters: `-MessageSource` (`auto`\|`local`\|`claude`, default `auto`), `-LocalMachines` (preference order; default T5820, T7920, GX10), `-LocalTimeoutMs`, `-LocalLoadTimeoutMs`, `-LocalMaxTokens`, `-ClaudeModel`, `-ClaudeTimeoutMs`, `-MaxDiffCharsPerCommit`, `-MaxCommitsPerRepo` (default 8; 1 = one commit per repo), `-DryRun`, `-SkipCustomerDomainCheck`, `-SkipIgnoredSourceCheck`, `-SkipPolyStringCaseCheck`, `-GateRepairAttempts` (default 3; 0 = report and end), `-GateRepairModel` (default `claude-sonnet-5-5`), `-GateRepairEffort` (default `medium`), `-GateRepairTimeoutMs`, `-SelfTest`

A failing pre-commit check aborts the whole run with nothing committed: customer-domain isolation, ignored source, PolyString case round-trips, design/task references (no skip switch), Python lint correctness (no skip switch). The last three are handed to a Claude repair agent first. Details, and the audit gate for each check: [README.md](README.md#commit-and-pushps1).
