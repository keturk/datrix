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

## `git\l-commit-and-push.ps1`

Builds `commit-messages.json` using a local Ollama model for each repo with uncommitted changes (plain-text messages; printed to console). Optional `-CommitAndPush` runs `commit-and-push.ps1` after writing the JSON.

| Mode | Command | Description |
|------|---------|-------------|
| **Generate JSON only** | `.\git\l-commit-and-push.ps1` | Default output: `commit-messages.json` under workspace root |
| **Generate then commit/push** | `.\git\l-commit-and-push.ps1 -CommitAndPush` | Writes JSON, then `commit-and-push.ps1` |

**Parameters:** `-OllamaBaseUrl`, `-OllamaModel`, `-OllamaTimeoutMs`, `-MessagesPath`, `-MaxDiffCharsPerRepo`, `-OllamaNumPredict`, `-CommitAndPush`

---

## `git\auto-commit-and-push.ps1`

**Fully automated commit-and-push workflow.** Invokes Claude Code CLI to analyze all repos, generate `commit-messages.json`, then automatically commits and pushes. This is the recommended way to commit across all Datrix repos.

| Mode | Command | Description |
|------|---------|-------------|
| **Auto (default)** | `.\git\auto-commit-and-push.ps1` | Claude analyzes, generates JSON, commits/pushes |
| **Auto with debug** | `.\git\auto-commit-and-push.ps1 -Dbg` | Same with verbose git output |

**Parameters:** `-MessagesPath` (default: D:\datrix\commit-messages.json), `-Dbg`

**Prerequisites:** Claude Code CLI must be installed and available in PATH (`claude` command).

---

## `git\commit-and-push.ps1`

Batch commits and pushes repos using messages from a JSON file. Format: `{ "datrix": "message", "datrix-common": "message", ... }`. Only repos with entries in the JSON are committed. Stops on first failure.

**Note:** This script is now called automatically by `auto-commit-and-push.ps1`. Use this directly only if you already have a pre-generated `commit-messages.json`.

| Mode | Command | Description |
|------|---------|-------------|
| **Default file** | `.\git\commit-and-push.ps1` | Uses `commit-messages.json` in current dir |
| **Explicit file** | `.\git\commit-and-push.ps1 commit-messages.json` | Specified JSON file |
| **Absolute path** | `.\git\commit-and-push.ps1 D:\datrix\commit-messages.json` | Full path to JSON |

**Parameters:** `-MessagesPath` (positional, default: commit-messages.json), `-Dbg`
