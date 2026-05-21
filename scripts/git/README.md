# Git Scripts

Git operations across all Datrix repositories.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/git/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `status.ps1` | Show git status for all repositories |
| `pull.ps1` | Pull latest changes for all repositories |
| `auto-commit-and-push.ps1` | **Recommended:** Fully automated commit-and-push using Claude Code CLI |
| `l-commit-and-push.ps1` | Build `commit-messages.json` via local Ollama; optional `-CommitAndPush` runs `commit-and-push.ps1` |
| `commit-and-push.ps1` | Batch commit and push using a JSON message file |

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

## auto-commit-and-push.ps1

**Recommended approach for committing and pushing across all Datrix repos.**

Fully automated workflow that invokes Claude Code CLI to analyze uncommitted changes, generate detailed commit messages, and automatically commit and push.

```powershell
# Fully automated: Claude analyzes → generates JSON → commits → pushes
.\auto-commit-and-push.ps1

# With debug output during commit/push phase
.\auto-commit-and-push.ps1 -Dbg
```

### How It Works

1. Invokes `claude --print` in CLI mode with prompt to analyze all repos
2. Claude scans for changes using git status and diff
3. Claude generates `D:\datrix\commit-messages.json` with detailed messages
4. Script verifies JSON was created successfully
5. Script automatically runs `commit-and-push.ps1` to commit and push

### Prerequisites

Claude Code CLI must be installed and available in PATH:

```bash
npm install -g @anthropic-ai/claude-code
```

Verify with: `claude --version`

### When to Use

- **Use auto-commit-and-push.ps1 when:** You want Claude to analyze changes and write commit messages automatically
- **Use commit-and-push.ps1 when:** You already have a pre-generated `commit-messages.json`
- **Use l-commit-and-push.ps1 when:** You prefer local Ollama models over Claude API

## l-commit-and-push.ps1

Generates `commit-messages.json` at the workspace root using a local Ollama model (one generate call per repo with changes). Prints each message to the console. Git commit and push is opt-in.

```powershell
# Write commit-messages.json only (from repo root)
.\l-commit-and-push.ps1

# Same, then run commit-and-push.ps1 with that file
.\l-commit-and-push.ps1 -CommitAndPush
```

See script comment-based help for `-OllamaBaseUrl`, `-OllamaModel`, `-MessagesPath`, and other parameters.

## commit-and-push.ps1

Commits and pushes changes across multiple repositories using a JSON file for commit messages.

### Usage

```powershell
# Use default commit-messages.json in current directory
.\commit-and-push.ps1

# Specify custom messages file
.\commit-and-push.ps1 D:\datrix\commit-messages.json

# Debug mode
.\commit-and-push.ps1 -Dbg
```

### Messages File Format

Create a `commit-messages.json` file:

```json
{
 "datrix-common": "feat: add new validation rules\n\nAdded email and URL validation.",
 "datrix-language": "fix: parser edge case with nested blocks",
 "datrix-common": "refactor: simplify template rendering"
}
```

- Keys are repository directory names
- Values are commit messages (can be multi-line)
- Only repositories with entries are committed
- Repositories without entries are skipped

### Behavior

1. Validates all repository keys exist in workspace
2. Removes any `.lock` files in `.git` folders
3. For each repo with a message:
 - `git add -A`
 - `git commit -F <temp-file>` (handles multi-line messages)
 - `git push`
4. Stops on first failure
