# Task Scripts

Task and bug tracking utilities for the Datrix workspace.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/tasks/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `todo.ps1` | List incomplete tasks and bugs |
| `completed.ps1` | List completed tasks and fixed bugs |
| `latest-phase.ps1` | Show latest development phase |
| `cleanup.ps1` | Clean up task artifacts |

## Task/Bug System

Tasks and bugs are tracked as markdown files in `.tasks/` and `.bugs/` folders within each project.

### Task Format

```markdown
# Task 123: Implement feature X

Description of the task...
```

When completed, prefix with `COMPLETED:`:

```markdown
# COMPLETED: Task 123: Implement feature X
```

### Bug Format

```markdown
# Bug 456: Fix crash on startup

Description of the bug...
```

When fixed, prefix with `FIXED:`:

```markdown
# FIXED: Bug 456: Fix crash on startup
```

## todo.ps1

Lists all incomplete tasks and unfixed bugs across the workspace.

```powershell
# List all incomplete items
.\todo.ps1

# Custom base directory
.\todo.ps1 -BaseDir D:\other\workspace

# Only items whose file name or title contains the filter string (case-insensitive)
.\todo.ps1 -Filter "parser"

# Debug mode
.\todo.ps1 -Dbg
```

### Output

```
========================================
Incomplete Tasks
========================================

=== datrix-common ===
 D:\datrix\datrix-common\.tasks\feature-x.md
 Title: Task 123: Implement feature X

=== datrix-language ===
 D:\datrix\datrix-language\.tasks\parser-fix.md
 Title: Task 456: Fix parser edge case

========================================
Total: 2 incomplete task(s) across 2 project(s)
========================================
```

## completed.ps1

Lists all completed tasks and fixed bugs.

```powershell
.\completed.ps1

# Only items whose file name or title contains the filter string (case-insensitive)
.\completed.ps1 -Filter "parser"

# Custom base directory
.\completed.ps1 -BaseDir D:\other\workspace
```

Same format as `todo.ps1` but shows items with `COMPLETED:` or `FIXED:` prefix. Supports the same `-Filter` and `-BaseDir` parameters as `todo.ps1`.

## latest-phase.ps1

Shows the latest development phase information.

```powershell
.\latest-phase.ps1
```

## cleanup.ps1

Cleans up task-related artifacts.

```powershell
.\cleanup.ps1
```
