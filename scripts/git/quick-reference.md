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

Pulls all git repositories under the workspace root.

| Mode | Command |
|------|---------|
| **Pull all** | `.\git\pull.ps1` |

**Parameters:** `-Dbg`

---

## `git\commit-and-push.ps1`

**One-pass commit-and-push across all Datrix repos.** For every repo with uncommitted changes, it generates a commit message and then stages, commits, and pushes it. No `commit-messages.json` is written. The message source is chosen automatically: if a local Ollama endpoint is reachable, messages come from the local model; otherwise it falls back to the Claude Code CLI. Stops on the first git failure.

| Mode | Command | Description |
|------|---------|-------------|
| **Auto (default)** | `.\git\commit-and-push.ps1` | Ollama if reachable, else Claude; commit + push |
| **Force local model** | `.\git\commit-and-push.ps1 -MessageSource ollama` | Require Ollama; error if unreachable |
| **Force Claude** | `.\git\commit-and-push.ps1 -MessageSource claude` | Use the Claude Code CLI |
| **Preview only** | `.\git\commit-and-push.ps1 -DryRun` | Print generated messages; do not commit |

**Parameters:** `-MessageSource` (`auto`\|`ollama`\|`claude`, default `auto`), `-OllamaBaseUrl`, `-OllamaModel`, `-OllamaTimeoutMs`, `-OllamaNumPredict`, `-ClaudeModel`, `-ClaudeTimeoutMs`, `-MaxDiffCharsPerRepo`, `-DryRun`, `-SkipCustomerDomainCheck`, `-SkipIgnoredSourceCheck`

**Prerequisites:** For the Claude fallback, the Claude Code CLI must be installed and available in PATH (`claude` command). For the Ollama path, the configured Ollama endpoint must be reachable.

### Customer-domain isolation runs first

Before a single message is generated or anything is staged, every dirty repo's pending changes are scanned against the hashed customer-term corpus (`scripts/config/customer-term-hashes.json`). One hit aborts the **whole run** with nothing committed — checked across all repos up front so a violation in the last repo cannot leave the first four already pushed. Violations are reported as `repo/path:line` with the matched token redacted; open the file:line to see it.

This is the seam where content actually enters a framework repo: every commit goes through this script's `git add -A`. Customer/project domain language must never reach one of these repos, and prose alone did not stop it — customer cloud-resource names and paths into a customer checkout were committed to a settings file through Claude Code permission entries nobody re-read.

`-SkipCustomerDomainCheck` bypasses it for a confirmed false positive; it prints a warning and commits regardless. To audit what is already committed (rather than what is pending), run `test\customer-domain-isolation-gate.ps1`. To register a new term, use that gate's `-AddTerm`.

### The ignored-source check runs next, still before anything is staged

The same seam asked in the opposite direction. The isolation check asks what a `git add -A` must not carry **in**; this one asks what it silently leaves **out**. Each dirty repo's working tree is compared against what `git add -A` would stage, and every file git refuses to stage must be a reviewed, scoped entry in `scripts/config/ignored-source-exemptions.json`. One unexplained file aborts the **whole run** with nothing committed and no message generated, reported as `repo/path  <- shadowed by <gitignore>:<line>: <pattern>` — the file and the rule together, because the file alone leaves the fix a hunt.

A package once carried the stock Python `.gitignore`'s **unanchored** `MANIFEST` line. Git matches an unanchored pattern at any depth and `core.ignorecase=true` here makes it case-insensitive, so it swallowed a `templates/manifest/` directory of shipped Jinja2 templates. Nothing was visible locally: the files were on disk, the tests passed, the emitted output compiled. The loss only appears after a clone or a wheel install, as a package that cannot generate — and by then the files are absent from history. `git add -A` is where that decision is made, so this is where it is checked.

The scanner runs its own non-vacuity self-test first; a self-test failure aborts the run rather than reporting a verdict nobody can trust. `-SkipIgnoredSourceCheck` bypasses the check for a confirmed false positive; it prints a warning and commits regardless. To audit the whole workspace rather than just the dirty repos, run `test\ignored-source-gate.ps1`.
