# Git Scripts

Git operations across all Datrix repositories.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/git/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `status.ps1` | Show git status for all repositories |
| `pull.ps1` | Pull latest changes for all repositories |
| `commit-and-push.ps1` | One-pass commit-and-push for all dirty repos; messages from local Ollama (if reachable) or the Claude Code CLI |

## status.ps1

Shows the git status of all repositories in the workspace.

```powershell
# Quick status (clean/has changes)
.\status.ps1

# Detailed status with changed files
.\status.ps1 -Detailed
```

### Output

```
datrix-common: clean
datrix-language: has changes
 Details:
 Branch: main
 Ahead: 2 commit(s)
 Changed files:
 M src/parser.py
 ?? new_file.py
```

## pull.ps1

Pulls latest changes from remote for all repositories.

```powershell
.\pull.ps1
```

## commit-and-push.ps1

**The single way to commit and push across all Datrix repos.**

For every repository with uncommitted changes, it generates a commit message and then stages, commits, and pushes that repo — in one pass, with no intermediate `commit-messages.json` file. A thin PowerShell wrapper delegates to `scripts/library/git/commit-and-push.py`, which holds the shared logic (change collection, message generation, and git commit/push).

```powershell
# Auto: local Ollama if reachable, else Claude Code CLI; commit + push
.\commit-and-push.ps1

# Force the local Ollama model (errors if Ollama is unreachable)
.\commit-and-push.ps1 -MessageSource ollama

# Force the Claude Code CLI
.\commit-and-push.ps1 -MessageSource claude

# Preview the generated messages without committing
.\commit-and-push.ps1 -DryRun
```

### How It Works

1. Probes the configured Ollama endpoint for reachability.
2. **Message source:**
   - If Ollama is reachable → one local-model generate call per dirty repo.
   - Otherwise → the Claude Code CLI generates the message per dirty repo (with read-only git/read tools scoped to that repo).
   - Generated messages pass a quality gate (no path dumps, no chat-style prose, concrete subject); a deterministic fallback is used if a model cannot produce a usable message.
3. For each dirty repo: removes stale `.lock` files, then `git add -A`, `git commit -F <temp-file>` (handles multi-line messages), `git push`.
4. Stops on the first git failure.

### Prerequisites

- **Ollama path:** the configured Ollama endpoint (default `http://10.94.0.100:11434`) must be reachable.
- **Claude fallback:** the Claude Code CLI must be installed and available in PATH:

  ```bash
  npm install -g @anthropic-ai/claude-code
  ```

  Verify with: `claude --version`

### Parameters

`-MessageSource` (`auto`\|`ollama`\|`claude`, default `auto`), `-OllamaBaseUrl`, `-OllamaModel`, `-OllamaTimeoutMs`, `-OllamaNumPredict`, `-ClaudeModel`, `-ClaudeTimeoutMs`, `-MaxDiffCharsPerRepo`, `-DryRun`. See the script comment-based help for defaults.
