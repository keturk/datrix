# Git Scripts

Git operations across all Datrix repositories. The commands, parameters and exit codes of each script
are in [quick-reference.md](quick-reference.md); this file holds what they do and how they decide.

Each `.ps1` here is rendered from the shared entrypoint template and runs a module of
`common/lib/datrix_scripts/git/`; each has a POSIX twin `.sh` beside it taking the same options as
`--kebab` flags, and each takes `-SelfTest` (the module's checks and the wrapper seam checks). No script
here runs `git stash`, `reset`, `checkout`, `restore` or `revert`; the self-tests of `status`, `pull`,
`pre-review`, `fix-line-endings` and `commit-and-push` scan for those forms in every git module and every
`datrix_scripts` module the git modules import (the shared scans commit-and-push runs call git too).

## `status.ps1`

Shows git status for all repositories under the workspace root: clean/has-changes per repo, or with
`-Detailed` the branch, ahead/behind and changed files.

Module: `datrix_scripts.git.status`; POSIX twin `git/status.sh` (`--detailed`, `--dbg`, `--self-test`).

## `pull.ps1`

Pulls all git repositories under the workspace root, printing git's output per repo, then one summary
grouping every repo by outcome: **Updated** (old..new, commit count), **Up to date**, **Conflict**
(unmerged paths listed), **Blocked by local changes** (the paths the pull would overwrite; nothing
merged — Jon's `/resolve-conflicts`), **Failed** (git's error line).

Each blocked path carries a verdict. It compares the local edit (HEAD vs the working tree) with the
incoming one (HEAD vs the fetched upstream) on HEAD line ranges, which is the first question a conflict
resolution asks:

| Verdict | Meaning |
|---------|---------|
| `OVERLAPS upstream at HEAD lines ...` | Both sides changed the same lines (within git's 3-line merge context): a real conflict |
| `DISJOINT: local a-b \| incoming c-d` | Both changed the file, in different places |
| `NOT CHANGED UPSTREAM` | Only the local side changed the file's content |
| `NO LOCAL CONTENT CHANGE` | The local difference is mode or line endings only (see `git\fix-line-endings.ps1`) |
| `UNTRACKED` | A local untracked file the incoming commits add; compare the two by hand |

**A repo left Conflict or Blocked is handed to a Claude agent.** After every repo has been pulled, each
one in either state gets an agent (`-ConflictRepairModel`, default `claude-sonnet-5-5`, at
`-ConflictRepairEffort`, default `medium`) whose whole prompt is `/resolve-conflicts <repo>`: the skill
runs as if Jon typed it, and the session is saved so `guard-forbidden-commands.py` finds the typed skill
in the transcript and allows `resolve-pull.ps1` and its path-limited stash. The agent has a shell, file
tools and the workspace's hooks; the hooks decide which git forms it may run. Afterwards the repo is
pulled again. On success it is reported from its HEAD before the first pull, so the commits the agent's
own pull brought in show as **Updated** (old..new, commit count) rather than Up to date, with a note
naming what the agent was handed: `blocked by local changes, resolved by the agent in N run(s)` or
`merge conflicts, resolved by the agent in N run(s)`. A run that leaves it needing attention is repeated
up to `-ConflictRepairAttempts` times (default 2); an agent that cannot run marks the repo Failed with
the reason; either way the other repos carry on. `-ConflictRepairAttempts 0` restores report-and-stop.
The skill's own frontmatter names an effort (`high`), which may take precedence over
`-ConflictRepairEffort` while the skill runs.

Module: `datrix_scripts.git.pull`; POSIX twin `git/pull.sh` (`--conflict-repair-attempts`,
`--conflict-repair-model`, `--conflict-repair-effort`, `--conflict-repair-timeout-ms`, `--self-test`).
The headless agent run is shared with `commit-and-push` in `datrix_scripts.claude_cli`
(`AgentRequest`, `run_agent`).

## `fix-line-endings.ps1`

Gives each modified file back the line endings its index copy has. A tool that writes a file back in the
other line-ending style turns a small edit into a whole-file rewrite and hides the real change. For every
file with unstaged modifications, it reads the file's own index blob (`git show :<path>`, read-only) and
rewrites **only the working copy's line terminators** to match it. Content is never changed, and nothing
is reverted, staged or checked out. Binary files and files that already match are skipped. A file whose
index copy itself mixes CRLF and LF is named and left as is. The committed side (every repo's catch-all
`* text=auto eol=lf` attribute rule, and no CRLF line in any index blob) is held by
`gates\repo-hygiene\line-ending-gate.ps1`.

Module: `datrix_scripts.git.fix_line_endings`; POSIX twin `git/fix-line-endings.sh` (`--repo`,
`--dry-run`, `--self-test`).

## `resolve-pull.ps1`

**Pulls repositories over uncommitted local work: the mechanical half of `/resolve-conflicts`.** Agents
may run it only once Jon has typed `/resolve-conflicts` in the session (`guard-forbidden-commands.py`);
Jon may run it from his own terminal at any time. Per repository whose upstream is ahead, it:

- measures the tracked overlap (local modifications ∩ incoming changes) and the untracked collisions (untracked files ∩ files the pull adds), and restores line endings (`fix-line-endings`) on paths whose only local difference is line endings
- shelves **only** the overlap (`git stash push -m "resolve-conflicts <repo> <stamp>" -- <paths>`) and sets aside each differing untracked collision under `<workspace>\.tmp\resolve-conflicts\<repo>\untracked\` (an identical one is deleted; the pull recreates it)
- pulls (`--ff-only`, or `--no-rebase --no-edit` when diverged), reapplies with `stash apply`, verifies, and drops the stash entry

A conflict stops with the markers in place and a packet at
`<workspace>\.tmp\resolve-conflicts\<repo>\conflicts.md`: each hunk's local, base and incoming text, with
a local model's merge draft (framework repos only, never a hunk carrying a registered customer term)
marked CHECKED only when it carries every line either side added. `-Finish` refuses while a merge or a
marker remains, unstages the shelved paths, proves every local added line and every set-aside line is in
the working tree, and only then drops the stash entry and the state (`state.json` in the same folder).
`-Merged <path>` makes a local line missing from a named path reported instead of refused.
`-SelfTest` runs the wrapper seam checks: the wrapper and its `.sh` twin are the templates rendered with
exactly the module's options.

## `pre-review.ps1`

**First-pass review of pending changes, run before `commit-and-push.ps1`** (the `/commit-and-push` skill
runs it as step 1). It checks only the lines pending changes ADD to Python files, across every repo with
uncommitted changes, reading each file's syntax tree on this machine in a few seconds.

Definite findings: `get-none` (a `.get(key, None)` silent fallback), `bare-except`, `except-pass`,
`todo-comment` (TODO/FIXME/XXX/HACK), `untyped-def` (a parameter or return with no annotation),
`placeholder` (a body of only `pass`, `...`, a docstring or `raise NotImplementedError`, with
Protocol/ABC classes and `@abstractmethod`/`@overload` exempt), and `syntax-error`. These alone decide
the exit code.

`-ModelReview` also asks a local model for advisory findings on non-test files. Each is kept only at high
confidence, on an added line, and quoting that line's code. On qwen3.6-35b that still left 44 findings
on 17.9k added lines, nearly all false positives, so it is off by default and never changes the exit
code.

Module: `datrix_scripts.git.pre_review`; POSIX twin `git/pre-review.sh` (`--model-review`,
`--local-machines`, `--llm-model`, `--llm-timeout`, `--self-test`).

## `pre-review-gate.ps1`

Behaviour checks for the first-pass pre-review (`datrix_scripts.git.pre_review`, wrapped by
`git\pre-review.ps1`), over real git repositories in a temporary directory. It covers:

- the diff parser
- every definite rule firing on added lines only, with planted old violations as the non-vacuity control and Protocol/ABC declarations exempt
- pending changes read from git (untracked files included, ignored files excluded)
- model findings dropped unless high-confidence, on an added line, and quoting that line
- the model review staying advisory and off test files, against a real loopback model server

Module: `datrix_scripts.git.pre_review_gate`; POSIX twin `git/pre-review-gate.sh` (`--only`,
`--harness-self-test`, `--self-test`, `--dbg`).

## `resolve-pull-gate.ps1`

Behaviour checks for `git\resolve-pull.ps1` (`datrix_scripts.git.resolve_pull`), over an origin repository and a
clone of it in a temporary directory; no real checkout is touched. It covers:

- a clean reapply shelving only the overlap and dropping the stash entry
- a conflict keeping its markers and writing the packet, and `-Finish` refusing until the markers are gone
- `-Finish` refusing a dropped local line unless its path is named in `-Merged`
- an untracked collision set aside, and refused until merged back
- a line-ending-only overlap restored instead of shelved
- the diff3 hunk parser (two- and three-sided)
- the merge draft checked against both sides, never sent for a non-framework repo or a hunk carrying a registered customer term, against a real loopback model server

`-SelfTest` runs the harness self-test and the wrapper seam checks (the form gate runners call). The run ends
on the `[GATE] resolve-pull PASSED|FAILED exit=<n> log=<path>` verdict line.

Module: `datrix_scripts.git.resolve_pull_gate`; POSIX twin `git/resolve-pull-gate.sh` (`--only`,
`--harness-self-test`, `--self-test`, `--dbg`).

## `commit-and-push.ps1`

**One-pass commit-and-push across all Datrix repos.** For every repo with uncommitted changes, it splits
the changes into themed change sets by area (a module and its tests together), generates one message per
set, commits each set separately, and pushes the repo once. No `commit-messages.json` is written. The
message source is chosen automatically: the local machines' Ollama servers are searched and what they
hold or can load is discovered; models already in memory are tried first, then a model Ollama can load,
and the first that answers generates the messages (one that fails hands over to the next); if none
answers, it falls back to the Claude Code CLI, run with no tools. Subjects are cropped to 72 characters.
Stops on the first git failure.

Module: `datrix_scripts.git.commit_and_push`; POSIX twin `git/commit-and-push.sh` (`--message-source`,
`--local-machines`, `--local-timeout-ms`, `--local-load-timeout-ms`, `--local-max-tokens`,
`--claude-model`, `--claude-timeout-ms`, `--max-diff-chars-per-commit`, `--max-commits-per-repo`,
`--dry-run`, `--skip-customer-domain-check`, `--skip-ignored-source-check`,
`--skip-poly-string-case-check`, `--self-test`).

**Prerequisites:** For the Claude fallback, the Claude Code CLI must be installed and available in PATH
(`claude` command; `npm install -g @anthropic-ai/claude-code`, verify with `claude --version`). For the
local path, at least one searched machine must run a model server that answers. The default machines, in
order, are `DEFAULT_LOCAL_MACHINES` in `common/lib/datrix_scripts/local_llm.py`.

### Customer-domain isolation runs first

Before a single message is generated or anything is staged, every dirty repo's pending changes are
scanned against the hashed customer-term corpus (`scripts/config/customer-term-hashes.json`). One hit
aborts the **whole run** with nothing committed — checked across all repos up front so a violation in the
last repo cannot leave the first four already pushed. Violations are reported as `repo/path:line` with
the matched token redacted; open the file:line to see it.

This is the seam where content actually enters a framework repo: every commit goes through this script's
`git add -A`. Customer/project domain language must never reach one of these repos, and prose alone did
not stop it — customer cloud-resource names and paths into a customer checkout were committed to a
settings file through Claude Code permission entries nobody re-read.

The script's `-SelfTest` proves the abort with a planted term (the corpus stores only digests): one hit
fails the whole run, the error names the file and line without printing the term, and nothing is staged
or committed.

`-SkipCustomerDomainCheck` bypasses it for a confirmed false positive; it prints a warning and commits
regardless. To audit what is already committed (rather than what is pending), run
`gates\repo-hygiene\customer-domain-isolation-gate.ps1`. To register a new term, use that gate's
`-AddTerm`.

### The ignored-source check runs next, still before anything is staged

The same seam asked in the opposite direction. The isolation check asks what a `git add -A` must not
carry **in**; this one asks what it silently leaves **out**. Each dirty repo's working tree is compared
against what `git add -A` would stage, and every file git refuses to stage must be a reviewed, scoped
entry in `scripts/config/ignored-source-exemptions.json`. One unexplained file aborts the **whole run**
with nothing committed and no message generated, reported as
`repo/path  <- shadowed by <gitignore>:<line>: <pattern>` — the file and the rule together, because the
file alone leaves the fix a hunt.

A package once carried the stock Python `.gitignore`'s **unanchored** `MANIFEST` line. Git matches an
unanchored pattern at any depth and `core.ignorecase=true` here makes it case-insensitive, so it
swallowed a `templates/manifest/` directory of shipped Jinja2 templates. Nothing was visible locally: the
files were on disk, the tests passed, the emitted output compiled. The loss only appears after a clone or
a wheel install, as a package that cannot generate — and by then the files are absent from history.
`git add -A` is where that decision is made, so this is where it is checked.

The scanner runs its own non-vacuity self-test first; a self-test failure aborts the run rather than
reporting a verdict nobody can trust. `-SkipIgnoredSourceCheck` bypasses the check for a confirmed false
positive; it prints a warning and commits regardless. To audit the whole workspace rather than just the
dirty repos, run `gates\repo-hygiene\ignored-source-gate.ps1`.

### The PolyString case round-trip check runs third, still before anything is staged

Every pending `.py` file in every dirty repo is parsed with `ast`, and any call to a
`datrix_common.utils.text` case function (`to_snake_case`, `to_camel_case`, `to_pascal_case`,
`to_kebab_case`, `to_screaming_snake_case` — by canonical name, import alias, or module attribute) whose
argument is `str(...)`-wrapped, bound by `NAME = str(...)` in the same scope, another case call, or an
`extract_simple_name(...)` call aborts the **whole run** with nothing committed, reported as
`repo/path:line:col  <kind>  to_x_case(...)  -- <fix>`. Every name the generator re-cases is a
`PolyString` that already carries `.snake`/`.camel`/`.pascal`/`.kebab`/`.screaming_snake`/`.simple`; the
round trip discards the variants, recomputes the word split, and hides from the next reader that the
value was a name. It reached more than a thousand sites while the only check was an on-demand Semgrep
warning. Held at a hard zero: there is no exemption file, because no shape has a legitimate instance — a
case function never needs a `str()` around its argument.

The scanner runs its own non-vacuity self-test first. `-SkipPolyStringCaseCheck` bypasses the check for
a confirmed false positive; it prints a warning and commits regardless. To audit the whole workspace
rather than just the pending files, run `gates\repo-hygiene\polystring-case-roundtrip-gate.ps1`.

### The design/task reference check runs last, still before anything is staged

Every dirty repo's pending files are scanned with the same matcher as
`gates\repo-hygiene\design-task-reference-gate.ps1`, its roots and scopes applied per file: a design-doc
or task-file reference (`task-NN-MM`, `task NN-MM`, the possessive `NN-MM's`, `design NNN`,
`design/NNN-slug`, `.tasks/phase-NN`) in any scanned extension under a package's `src`, `tests`, `docs`
or `scripts`, and an item label (a capital letter and digits, in parentheses or before a colon) in a
package's `src`, `tests` or `scripts` or the showcase repo's `scripts`. One hit aborts the **whole run**
with nothing committed, reported as `[label] repo/path:line: text`. Design docs and task files are
gitignored and numbered per machine, so a committed reference dangles after a clone. There is **no skip
switch** and no exemption file beyond the gate's own `ALLOWLIST` and `LABEL_TOKEN_EXCEPTIONS`.

The scanner runs its own non-vacuity self-test first; a self-test failure aborts the run. To audit the
whole workspace rather than just the pending files, run
`gates\repo-hygiene\design-task-reference-gate.ps1`.

### The Python lint-correctness check runs after it, still before anything is staged

Each dirty repo's pending `.py` files (what a `git add -A` would stage; deletions excluded, and the
checked-in output under `examples/**/generated/` skipped — that is generator output, held by the
generators' own tests and replaced on regeneration; and the repo-root `vulture_whitelist.py` skipped —
that is Vulture's input, a list of names nothing binds) are linted with `ruff check --select F` and
`ruff check --select E302,E305 --preview`, each run from that repo's root so its own `per-file-ignores`
apply. Any finding — an unused import, an undefined name, a test function silently shadowed by a
same-named redefinition, a top-level def/class without two blank lines before or after it — aborts the
**whole run** with nothing committed, reported as `repo/path:line:col CODE message`. Checked across all
repos up front so a finding in the last repo cannot leave the first four already pushed. This is the
per-change form of "lint only the files you edited", enforced rather than remembered. There is **no skip
switch** and no baseline: a finding that is genuinely required (an import kept for a documented side
effect) is suppressed on its own line with `# noqa: <code>` and the reason.

The scanner runs its own non-vacuity self-test first (a planted F401 + F821 must be seen, a planted
E302 + E305 must be seen, a clean package must report zero, a fixture `per-file-ignores` must suppress
the F401 only); a self-test failure aborts the run. To audit the whole workspace rather than just the
pending files, run `gates\repo-hygiene\python-lint-correctness-gate.ps1`.

### A failed gate is handed to a Claude agent, then the run continues

When the PolyString, design/task-reference or Python lint-correctness check finds problems in the
pending files, the run no longer ends with the report. The report goes to a Claude Code agent
(`-GateRepairModel`, default `claude-sonnet-5-5`, at `-GateRepairEffort`, default `medium`) that reads,
searches and edits files under the workspace's own CLAUDE.md and hooks. It has **no shell**: it cannot
stage, commit, push or run this script, and it is told never to edit a gate, an exemption file, a
baseline or a term corpus. The brief already carries the code around every flagged line (read by the
script), and the agent may call the read-only code-index tools (`find_symbol`, `find_references`,
`find_canonical`, `outline`, `search`) and `ask_files` of the local-model server, so it looks a
definition up instead of grepping and a local model can read a large file for it. Afterwards the dirty
repos are found again and **every** check re-runs; the re-run is the proof, not the agent's summary. The
run continues to messages, commits and pushes once the checks pass. A repair that leaves the gate failing
is retried up to `-GateRepairAttempts` times (default 3, the previous summary handed to the next); then
the run ends with the report as before. `-GateRepairAttempts 0` restores report-and-stop, and `-DryRun`
never repairs.

Not handed over: the customer-domain check (its report redacts the matched term on purpose) and the
ignored-source check (fixed by loosening a `.gitignore` rule or the exemption file, which a person
decides), and any check that could not run or failed its own self-test. Module:
`datrix_scripts.git.gate_repair`.

### How `commit-and-push.ps1` works

1. Finds the dirty repos and runs the pre-commit checks (customer-domain isolation, ignored source, PolyString case round-trips) across all of them before anything is generated or staged.
2. **Message source:**
   - Searches each local machine (`-LocalMachines`) for an Ollama server on port 11434 — all machines in parallel. Ollama is the only model server the local machines run. Nothing about a machine's models is configured: what answers, what it holds in memory and what it could load are discovered on every run. The search, readiness and failover live in `common/lib/datrix_scripts/local_llm.py`, which every local-model script in `scripts/` shares.
   - Candidates, best first: only the fast models of `OLLAMA_LOAD_PREFERENCE` (`common/lib/datrix_scripts/local_llm.py`), in that order — already in memory first, else loaded where installed. A large model resident for other work (the GX10's 120B) is never used for a commit message.
   - The first candidate is readied before any change set: its model is loaded (or a loaded one's keep-alive renewed) under `-LocalLoadTimeoutMs`, so a multi-minute cold load is not charged to a generate call.
   - A candidate that fails to ready or generate (an exhausted GPU, a model that cannot load) is dropped for the rest of the run and the next one takes over.
   - If nothing was found, or every candidate has failed → the Claude Code CLI generates the messages. It runs as a pure text call: no tools, `--safe-mode` (no workspace CLAUDE.md, hooks or skills), and its own system prompt. With `-MessageSource local` the run errors instead.
   - Reasoning models are asked to skip reasoning (Ollama `think=false`, sent only to a model with the `thinking` capability): a commit message needs none, and it multiplies generate time.
3. **Themed change sets:** each repo's dirty paths (untracked included, `.gitignore` honoured) are grouped by area. Container directories — `src/<package>`, `tests/<tier>`, `scripts`, `examples` — are stepped through, so `src/<pkg>/generators/x.py` and `tests/unit/generators/test_x.py` share the `generators` set and a feature lands in one commit with its tests. Past `-MaxCommitsPerRepo` sets, the smallest are folded into one `other changes` commit.
4. **One message per set:** the model sees only that set's diff and is told the rest is committed separately. Messages pass a quality gate (English only, no path dumps, no chat-style prose, concrete subject). A subject over 72 characters is cropped to 72 and the message accepted. If no backend produces a usable message, a model-free message states only the area and file counts — never a guessed description.
5. For each set: removes stale `.lock` files, `git add -A` over exactly the set's paths, then `git commit` restricted to those paths, so nothing else in the index rides along. Each repo is pushed once after its sets are committed.
6. Stops on the first git failure.
