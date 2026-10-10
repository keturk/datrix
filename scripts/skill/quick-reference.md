# Skill Scripts Quick Reference

Scripts that exist for the agent skills under `.claude/skills/`: running skills as headless steps on their own models, and the mechanical skill phases done by a script or a local model. Python lives in `skill/lib/`.

## Headless skill chains: `skill\implement-design.ps1`, `skill\implement-design-direct.ps1`, `skill\skill-chain.ps1`

**Run skills one after another as headless `claude -p` steps, each on its own skill's `model:`/`effort:`.** A skill invoked from inside another skill runs on the caller's model; a typed slash command switches to the skill's own. Each step here is a typed slash command in its own run, with the workspace's hooks, CLAUDE.md and guards. The shared step runner is `skill\SkillChain.psm1`. Needs the workspace trusted in `~/.claude.json` (`hasTrustDialogAccepted`), or headless runs ignore `settings.json`'s permissions.

| Mode | Command | Description |
|------|---------|-------------|
| **Implement a design, tasks path** | `.\skill\implement-design.ps1 -Design "D:\datrix\design\<file>.md"` | operationalize → orchestrate → verify → absorb |
| **Resume it after a question** | `.\skill\implement-design.ps1 -Design "<file>" -StartAt orchestrate -Phase 52` | Start at `orchestrate`, `verify` or `absorb` (needs `-Phase`) |
| **Implement a design, direct path** | `.\skill\implement-design-direct.ps1 -Design "D:\datrix\design\<file>.md"` | `/implement-design-direct` with `STOP AFTER: implement` → verify → absorb |
| **Resume it after a question** | `.\skill\implement-design-direct.ps1 -Design "<file>" -StartAt verify` | Start at `implement`, `verify` or `absorb` (after `implement`, its ledger must exist) |
| **Any sequence** | `.\skill\skill-chain.ps1 "/fix-codegen-python <index.json>" "/commit-and-push"` | Prompts in order; stops at the first error |
| **One session throughout** | append `-Resume` | Carry one session through every step instead of a fresh one per step |
| **Preview** | append `-DryRun` | Print the steps; run none |
| **Summary lines only** | append `-Quiet` | By default each agent message, tool call and refused tool call is printed as it happens; `-Quiet` shows only each step's prompt and summary |

The design scripts check the result between steps themselves; no model decides it:
- `implement-design.ps1`: operationalize must create a new phase (`latest-phase.ps1` before/after; otherwise it stopped for a decision). The phase is closed only when `phase-status.ps1` shows every task completed with no How-Solved red flag and the design's `Status:` reads Implemented; otherwise the orchestrator runs again.
- `implement-design-direct.ps1`: the implement step keeps its ledger at `D:\datrix\.tmp\implement-direct-<design file name>.md`. It is done only when the ledger has no unchecked unit and a `## Files changed` section. No ledger means it stopped at its gate for a decision; unchecked units mean implement runs again from the ledger.
- Both: absorb runs only after verify replies `Design conformance: PROVEN`. The verdict is read from every reply of the verify session's transcript, not only the last (a Stop hook that refuses a reply makes the session send another), and `.claude/checklists/verify-verdict.json` refuses a `/verify-implementation` turn that ends without the line. On INCOMPLETE, the implementing step (orchestrator, or implement with `GAPS:` set to verify's saved report) runs again, then verify. On PROVEN, verify's replies are kept at `D:\datrix\.tmp\verify-proven-<design file name>.md` and passed to `/absorb-design` as `VERIFIED:`, its licence to delete the design whatever the design's own `Status:` line says; `-StartAt absorb` stops with exit 1 when that file is missing or not PROVEN. Without `-KeepSource`, absorb must have deleted the design; otherwise it stopped at a question.

**Fresh vs `-Resume`.** A fresh step pays the workspace start-up context (about 26k tokens, mostly served from the prompt cache when the model repeats) plus the mandatory reads, and starts with its context window free. `-Resume` re-reads nothing, but every turn of every step re-reads all previous steps' transcript, and on a model change that whole transcript is written to the cache again at the new model's price. The design steps hand over through files (tasks, ledger, reports), so fresh is the default.

**From Git Bash**, set `MSYS_NO_PATHCONV=1` for `skill-chain.ps1`, or a leading `/` in a prompt is rewritten into a Windows path.

**Parameters:** `-Design` (or the first positional argument), `-StartAt`, `-KeepSource`, `-MaxRounds` (default 3) for the design scripts, `-Phase` for `implement-design.ps1`; the prompts as positional arguments for `skill-chain.ps1`. All three: `-Resume`; `-PermissionMode auto|acceptEdits|dontAsk|bypassPermissions` (default `auto`; the guards run in every mode); `-MaxBudgetUsd` (per step, list price); `-DryRun`; `-Quiet`. Logs: `D:\datrix\.tmp\skill-chain\<timestamp>\` (each step's result `.json`, every streamed event `.stream.jsonl`, stderr, and each INCOMPLETE verify report). **Exit codes:** 0 done; 1 a step ended in error or a check failed; 2 a step stopped for a decision only Jon can make (its reply and session id are printed).

## `skill\implement-finding.ps1`

**Drain the findings inbox one finding at a time: one session per finding, closed before the next starts.** The multi-finding form of `/implement-finding`. Per finding, in name order, one fresh headless `/implement-finding` session (via `skill\SkillChain.psm1`, started with `--model`/`--effort`) checks the finding against the code and, when it still holds, fixes it (code, tagged test, targeted runs, docs, pointers from other findings). It ends `Finding fix: ALREADY RESOLVED`, `DONE` or `BLOCKED B<n>` and never deletes the finding itself. The script then runs `finding-close`: never while another findings file names the finding, and after `DONE` only when the session's last foreground `test.ps1` run passed, read from the step's `.stream.jsonl` — not a model's word.

| Mode | Command | Description |
|------|---------|-------------|
| **First 10 findings** | `.\skill\implement-finding.ps1` | One session each, on Opus |
| **Fewer** | `.\skill\implement-finding.ps1 -Count 3` | The first 3 by name |
| **Given files** | `.\skill\implement-finding.ps1 -Finding "D:\datrix\reports\finding\<file>.md"` | Instead of the first `-Count` |
| **Preview** | append `-DryRun` | List the findings and print the steps; run none |

**Parameters:** `-Count` (default 10), `-Finding`, `-Dir` (default `<workspace>\reports\finding`), `-Model` (default `claude-opus-5-5`), `-Effort` (default `high`), `-PermissionMode`, `-MaxBudgetUsd`, `-DryRun`, `-Quiet`. Step logs: `D:\datrix\.tmp\skill-chain\<timestamp>\`. A session ending `Finding fix: BLOCKED B<n>` stops that finding and the chain moves to the next. **Exit codes:** 0 every finding deleted; 1 a session erred, replied with no outcome line, or a finding was left in place; 2 no failure, but a session stopped for a decision only Jon can make.

The checks live in `lib\implement_finding.py` and run as the `skill-assist.ps1` commands `finding-select` and `finding-close` (below); `/implement-finding` typed by hand calls `finding-close` itself.

## `skill\skill-assist.ps1`

**The mechanical phases of agent skills, done by a script or a local model instead of a Claude model.** Each command writes its output to `d:\datrix\.tmp\assist\` and prints the path with a one-line summary. Exact checks are exact; whatever a local model writes is checked against its inputs (citations and quotes against what it was sent, set comparisons against the source) and is marked as a lead. The skill keeps every verdict. Wrapper over `skill/lib/skill_assist.py`; the logic is in `skill/lib/`.

| Command | Skill phase it serves | What it produces |
|---------|-----------------------|------------------|
| `context-digest --phase N` | `/task-orchestrator` shared-context pre-read | Per package of the phase: the directories its tasks touch, each module with its first docstring line (or the index's summary), files a task names marked, files not yet created marked. From the code index; no model. Fits 400 lines |
| `readiness --phase N [--no-model]` | `/task-orchestrator` 1e readiness audit (dimensions 3, 4, 6) | Exact: dependency edges the graph lacks (a not-yet-existing file read or co-created without an order) and `## Codebase Context` dotted names the index cannot resolve. Lead: for each task whose edit sites all exist, a local model's SATISFIED / NOT SATISFIED / UNCLEAR on its acceptance property, citations checked. `validate-task.ps1` stays the citation and orientation check |
| `findings-index [--dir D]` | `/consolidate-findings` Phases 1–3; `/merge-findings` Phase 1 | Every findings file split into atomic findings (seam, packages, defect, citations) in one table sorted by seam; per file, citations no finding carries and citations the model invented |
| `findings-check --delete F... [--dir D] [--keep-raw]` | `/consolidate-findings` Phase 5; `/merge-findings` Phase 4 (with `--keep-raw`) | Exact: every `path:line` and backticked path of the files to delete appears in a remaining file; every `**Related:**` pointer resolves; no mojibake; no raw file left un-superseded (waived by `--keep-raw`, since a duplicate merge keeps every distinct raw file) |
| `finding-select [--count N] [--dir D]` | `/implement-finding` selection | Exact: the first N (default 10) `*.md` findings files by name, one path per line |
| `finding-close --finding F [--session-log L]` | `/implement-finding`, `implement-finding.ps1` delete | Exact: deletes F unless another findings file still names it; with `L` (a step's `.stream.jsonl`), also unless the session ran no foreground `test.ps1` or its last one did not pass (a non-zero exit, a result reporting failed/erroring tests, or output piped through a filter, which hides the exit code). Exit 0 deleted; 2 kept (the reasons are listed); 1 F does not exist |
| `checklist --design PATH` | `/verify-implementation` Phase 1 | The design's requirements (id, sentence, surfaces, cited lines) drafted by a local model; an item whose quote is not at its lines is flagged; every requirement-bearing line (a decision id or must/never/always/shall/required/forbidden/fail closed/fail loud) that no item covers is listed |
| `absorb-transfer --design PATH --target T...` | `/absorb-design` Phase 3 | Per design section: PRESENT / PARTIAL / MISSING in the target docs (framework repos), with checked citations |
| `absorb-references --design PATH [--also P...]` | `/absorb-design` Phase 4 | Exact: every line in the framework repos (and the extra paths) naming the design's file name, stem, title or number in a design-reference form. `.tasks` is not searched |
| `bug-resolution --report R --repo P... [--file F...] ...` | `/fix-bug-report` Phase 3 | The Resolution section: the Changes Made table from `git diff HEAD` plus untracked files (a framework file's row is a model's one-line summary of its diff; any other repo's row is the diff's shape and hunk functions, and nothing of it is sent to a model) and the facts passed (`--status`, `--fix-type`, `--exhibiting`, `--reached`, `--verification "profile|regenerated|artifact|result"`, or `--reason` + `--notes` when unresolved). A draft by default; `--append` appends it, refusing a report that already has one |

**What is sent to a model.** `checklist`, `absorb-transfer` and `findings-index` send design docs and findings files, which the MCP tools refuse; `readiness` and `absorb-transfer` read framework-repo files through the MCP tools' own scope. Every line is checked against the customer-term corpus first and withheld when it carries a registered term; without the corpus nothing is sent. `bug-resolution` sends a diff only for a framework repository, and never one that carries a term.

**Parameters:** the command, then its own python-style arguments; for the model commands the shared local-model flags `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (seconds, default 300).

**Exit codes:** 0 done; 1 the request could not be carried out; 2 the check found something to act on (`findings-check` FAIL, `finding-close` kept the finding, `absorb-transfer` partial/missing, `absorb-references` found lines); 3 no local model answered — do that phase yourself, as the skill did before the assist.

## `skill\skill-assist-gate.ps1`

**The gate for the skill assists:** every `skill/lib/` module and the `skill-assist.ps1` command line, checked against real files and a stand-in local model server, with no network model. Run it after changing anything under `skill/lib/`.

| Mode | Command |
|------|---------|
| **Run every check** | `.\skill\skill-assist-gate.ps1` |
| **One check** | `.\skill\skill-assist-gate.ps1 -Only <check name>` |
| **Prove the harness fails a broken check** | `.\skill\skill-assist-gate.ps1 -HarnessSelfTest` |

**Exit codes:** 0 every check passed; 1 a check failed.
