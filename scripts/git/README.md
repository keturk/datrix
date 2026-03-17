# Git Scripts

Git operations across all Datrix repositories.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/git/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `status.ps1` | Show git status for all repositories |
| `pull.ps1` | Pull latest changes for all repositories |
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
