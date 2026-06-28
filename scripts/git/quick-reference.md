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

**Parameters:** `-MessageSource` (`auto`\|`ollama`\|`claude`, default `auto`), `-OllamaBaseUrl`, `-OllamaModel`, `-OllamaTimeoutMs`, `-OllamaNumPredict`, `-ClaudeModel`, `-ClaudeTimeoutMs`, `-MaxDiffCharsPerRepo`, `-DryRun`

**Prerequisites:** For the Claude fallback, the Claude Code CLI must be installed and available in PATH (`claude` command). For the Ollama path, the configured Ollama endpoint must be reachable.
