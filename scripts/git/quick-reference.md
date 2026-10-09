# Quick Reference — Git Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## `git\status.ps1`

Shows git status for all repositories under the workspace root.

| Mode | Command | Description |
|------|---------|-------------|
| **Summary** | `.\git\status.ps1` | Clean/has-changes per repo |
| **Detailed** | `.\git\status.ps1 -Detailed` | Branch, ahead/behind, changed files |

**Parameters:** `-Detailed`, `-Dbg`

---

## `git\pull.ps1`

Pulls all git repositories under the workspace root (wraps `git\lib\pull.py`), printing git's output per repo, then one summary grouping every repo by outcome: **Updated** (old..new, commit count), **Up to date**, **Conflict** (unmerged paths listed), **Blocked by local changes** (the paths the pull would overwrite; nothing merged — Jon's `/resolve-conflicts`), **Failed** (git's error line).

| Mode | Command |
|------|---------|
| **Pull all** | `.\git\pull.ps1` |

**Parameters:** none.

**Exit codes:** 0 = every repo updated or up to date, 1 = at least one conflicted, was blocked or failed, 2 = the run could not start.

---

## `git\pre-review.ps1`

**First-pass review of pending changes, run before `commit-and-push.ps1`** (the `/commit-and-push` skill runs it as step 1). It checks only the lines pending changes ADD to Python files, across every repo with uncommitted changes, reading each file's syntax tree on this machine in a few seconds.

Definite findings: `get-none` (a `.get(key, None)` silent fallback), `bare-except`, `except-pass`, `todo-comment` (TODO/FIXME/XXX/HACK), `untyped-def` (a parameter or return with no annotation), `placeholder` (a body of only `pass`, `...`, a docstring or `raise NotImplementedError`, with Protocol/ABC classes and `@abstractmethod`/`@overload` exempt), and `syntax-error`. These alone decide the exit code.

`-ModelReview` also asks a local model for advisory findings on non-test files. Each is kept only at high confidence, on an added line, and quoting that line's code. On qwen3.6-35b that still left 44 findings on 17.9k added lines, nearly all false positives, so it is off by default and never changes the exit code.

| Mode | Command | Description |
|------|---------|-------------|
| **Review** | `.\git\pre-review.ps1` | Definite checks over pending added lines |
| **With model** | `.\git\pre-review.ps1 -ModelReview` | Plus advisory local-model findings |

**Parameters:** `-ModelReview`, and with it `-LocalMachines`, `-LlmModel`, `-LlmTimeout` (default 180)

**Exit codes:** 0 = no definite findings, 1 = definite findings (listed as `file:line rule: explanation`), 2 = the review could not run.

---

## `git\pre-review-gate.ps1`

Behaviour checks for the first-pass pre-review (`git/lib/pre_review.py`, wrapped by `git\pre-review.ps1`), over real git repositories in a temporary directory. It covers:

- the diff parser
- every definite rule firing on added lines only, with planted old violations as the non-vacuity control and Protocol/ABC declarations exempt
- pending changes read from git (untracked files included, ignored files excluded)
- model findings dropped unless high-confidence, on an added line, and quoting that line
- the model review staying advisory and off test files, against a real loopback model server

| Mode | Command | Description |
|------|---------|-------------|
| **Run the gate** | `.\git\pre-review-gate.ps1` | Run every check |
| **One area** | `.\git\pre-review-gate.ps1 -Only check_model` | Checks whose name starts with the prefix |
| **Harness self-test** | `.\git\pre-review-gate.ps1 -HarnessSelfTest` | Prove the harness reports a forced failure |

**Parameters:** `-Only`, `-HarnessSelfTest`, `-Dbg`

**Exit codes:** 0 = every check passed, 1 = a check failed, 2 = usage error.

---

## `git\commit-and-push.ps1`

**One-pass commit-and-push across all Datrix repos.** For every repo with uncommitted changes, it splits the changes into themed change sets by area (a module and its tests together), generates one message per set, commits each set separately, and pushes the repo once. No `commit-messages.json` is written. The message source is chosen automatically: the local machines' Ollama servers are searched and what they hold or can load is discovered; models already in memory are tried first, then a model Ollama can load, and the first that answers generates the messages (one that fails hands over to the next); if none answers, it falls back to the Claude Code CLI, run with no tools. Subjects are held to 72 characters. Stops on the first git failure.

| Mode | Command | Description |
|------|---------|-------------|
| **Auto (default)** | `.\git\commit-and-push.ps1` | First local model that answers, else Claude; commit + push |
| **Force local model** | `.\git\commit-and-push.ps1 -MessageSource local` | Require a local model; error if none answers |
| **Force Claude** | `.\git\commit-and-push.ps1 -MessageSource claude` | Use the Claude Code CLI |
| **Preview only** | `.\git\commit-and-push.ps1 -DryRun` | Print generated messages; do not commit |

**Parameters:** `-MessageSource` (`auto`\|`local`\|`claude`, default `auto`), `-LocalMachines` (host names or IPs to search, preference order; default T5820, T7920, GX10), `-LocalTimeoutMs`, `-LocalLoadTimeoutMs`, `-LocalMaxTokens`, `-ClaudeModel`, `-ClaudeTimeoutMs`, `-MaxDiffCharsPerCommit`, `-MaxCommitsPerRepo` (default 8; 1 = one commit per repo), `-DryRun`, `-SkipCustomerDomainCheck`, `-SkipIgnoredSourceCheck`, `-SkipPolyStringCaseCheck`

**Prerequisites:** For the Claude fallback, the Claude Code CLI must be installed and available in PATH (`claude` command). For the local path, at least one searched machine must run a model server that answers.

### Customer-domain isolation runs first

Before a single message is generated or anything is staged, every dirty repo's pending changes are scanned against the hashed customer-term corpus (`scripts/config/customer-term-hashes.json`). One hit aborts the **whole run** with nothing committed — checked across all repos up front so a violation in the last repo cannot leave the first four already pushed. Violations are reported as `repo/path:line` with the matched token redacted; open the file:line to see it.

This is the seam where content actually enters a framework repo: every commit goes through this script's `git add -A`. Customer/project domain language must never reach one of these repos, and prose alone did not stop it — customer cloud-resource names and paths into a customer checkout were committed to a settings file through Claude Code permission entries nobody re-read.

`-SkipCustomerDomainCheck` bypasses it for a confirmed false positive; it prints a warning and commits regardless. To audit what is already committed (rather than what is pending), run `gates\repo-hygiene\customer-domain-isolation-gate.ps1`. To register a new term, use that gate's `-AddTerm`.

### The ignored-source check runs next, still before anything is staged

The same seam asked in the opposite direction. The isolation check asks what a `git add -A` must not carry **in**; this one asks what it silently leaves **out**. Each dirty repo's working tree is compared against what `git add -A` would stage, and every file git refuses to stage must be a reviewed, scoped entry in `scripts/config/ignored-source-exemptions.json`. One unexplained file aborts the **whole run** with nothing committed and no message generated, reported as `repo/path  <- shadowed by <gitignore>:<line>: <pattern>` — the file and the rule together, because the file alone leaves the fix a hunt.

A package once carried the stock Python `.gitignore`'s **unanchored** `MANIFEST` line. Git matches an unanchored pattern at any depth and `core.ignorecase=true` here makes it case-insensitive, so it swallowed a `templates/manifest/` directory of shipped Jinja2 templates. Nothing was visible locally: the files were on disk, the tests passed, the emitted output compiled. The loss only appears after a clone or a wheel install, as a package that cannot generate — and by then the files are absent from history. `git add -A` is where that decision is made, so this is where it is checked.

The scanner runs its own non-vacuity self-test first; a self-test failure aborts the run rather than reporting a verdict nobody can trust. `-SkipIgnoredSourceCheck` bypasses the check for a confirmed false positive; it prints a warning and commits regardless. To audit the whole workspace rather than just the dirty repos, run `gates\repo-hygiene\ignored-source-gate.ps1`.

### The PolyString case round-trip check runs third, still before anything is staged

Every pending `.py` file in every dirty repo is parsed with `ast`, and any call to a `datrix_common.utils.text` case function (`to_snake_case`, `to_camel_case`, `to_pascal_case`, `to_kebab_case`, `to_screaming_snake_case` — by canonical name, import alias, or module attribute) whose argument is `str(...)`-wrapped, bound by `NAME = str(...)` in the same scope, another case call, or an `extract_simple_name(...)` call aborts the **whole run** with nothing committed, reported as `repo/path:line:col  <kind>  to_x_case(...)  -- <fix>`. Every name the generator re-cases is a `PolyString` that already carries `.snake`/`.camel`/`.pascal`/`.kebab`/`.screaming_snake`/`.simple`; the round trip discards the variants, recomputes the word split, and hides from the next reader that the value was a name. It reached more than a thousand sites while the only check was an on-demand Semgrep warning. Held at a hard zero: there is no exemption file, because no shape has a legitimate instance — a case function never needs a `str()` around its argument.

The scanner runs its own non-vacuity self-test first. `-SkipPolyStringCaseCheck` bypasses the check for a confirmed false positive; it prints a warning and commits regardless. To audit the whole workspace rather than just the pending files, run `gates\repo-hygiene\polystring-case-roundtrip-gate.ps1`.

### The design/task reference check runs last, still before anything is staged

Every dirty repo's pending files are scanned with the same matcher as `gates\repo-hygiene\design-task-reference-gate.ps1`, its roots and scopes applied per file: a design-doc or task-file reference (`task-NN-MM`, `task NN-MM`, the possessive `NN-MM's`, `design NNN`, `design/NNN-slug`, `.tasks/phase-NN`) in any scanned extension under a package's `src`, `tests`, `docs` or `scripts`, and an item label (a capital letter and digits, in parentheses or before a colon) in a package's `src`, `tests` or `scripts` or the showcase repo's `scripts`. One hit aborts the **whole run** with nothing committed, reported as `[label] repo/path:line: text`. Design docs and task files are gitignored and numbered per machine, so a committed reference dangles after a clone. There is **no skip switch** and no exemption file beyond the gate's own `ALLOWLIST` and `LABEL_TOKEN_EXCEPTIONS`.

The scanner runs its own non-vacuity self-test first; a self-test failure aborts the run. To audit the whole workspace rather than just the pending files, run `gates\repo-hygiene\design-task-reference-gate.ps1`.

### The Python lint-correctness check runs after it, still before anything is staged

Each dirty repo's pending `.py` files (what a `git add -A` would stage; deletions excluded, and the checked-in output under `examples/**/generated/` skipped — that is generator output, held by the generators' own tests and replaced on regeneration; and the repo-root `vulture_whitelist.py` skipped — that is Vulture's input, a list of names nothing binds) are linted with `ruff check --select F`, run from that repo's root so its own `per-file-ignores` apply. Any pyflakes finding — an unused import, an undefined name, a test function silently shadowed by a same-named redefinition — aborts the **whole run** with nothing committed, reported as `repo/path:line:col CODE message`. Checked across all repos up front so a finding in the last repo cannot leave the first four already pushed. This is the per-change form of "lint only the files you edited", enforced rather than remembered. There is **no skip switch** and no baseline: a finding that is genuinely required (an import kept for a documented side effect) is suppressed on its own line with `# noqa: <code>` and the reason.

The scanner runs its own non-vacuity self-test first (a planted F401 + F821 must be seen, a clean package must report zero, a fixture `per-file-ignores` must suppress the F401 only); a self-test failure aborts the run. To audit the whole workspace rather than just the pending files, run `gates\repo-hygiene\python-lint-correctness-gate.ps1`.
