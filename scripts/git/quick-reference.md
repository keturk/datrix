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

## `git\commit-and-push.ps1`

Batch commits and pushes repos using messages from a JSON file. Format: `{ "datrix": "message", "datrix-common": "message", ... }`. Only repos with entries in the JSON are committed. Stops on first failure.

| Mode | Command | Description |
|------|---------|-------------|
| **Default file** | `.\git\commit-and-push.ps1` | Uses `commit-messages.json` in current dir |
| **Explicit file** | `.\git\commit-and-push.ps1 commit-messages.json` | Specified JSON file |
| **Absolute path** | `.\git\commit-and-push.ps1 D:\datrix\commit-messages.json` | Full path to JSON |

**Parameters:** `-MessagesPath` (positional, default: commit-messages.json), `-Dbg`
