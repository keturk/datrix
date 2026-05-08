# Quick Reference — Task Management Scripts

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## `tasks\todo.ps1`

Lists incomplete tasks (without `COMPLETED:` prefix) and incomplete bugs (without `FIXED:` prefix) from `.tasks/` and `.bugs/` folders across all projects.

| Mode | Command | Description |
|------|---------|-------------|
| **List all** | `.\tasks\todo.ps1` | All incomplete tasks and bugs |
| **Filter** | `.\tasks\todo.ps1 -Filter "parser"` | Filter by filename or title (case-insensitive) |
| **Custom base dir** | `.\tasks\todo.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Filter`, `-Dbg`

---

## `tasks\completed.ps1`

Lists completed tasks (`COMPLETED:` prefix) and fixed bugs (`FIXED:` prefix) from `.tasks/` and `.bugs/` folders.

| Mode | Command | Description |
|------|---------|-------------|
| **List all** | `.\tasks\completed.ps1` | All completed tasks and fixed bugs |
| **Filter** | `.\tasks\completed.ps1 -Filter "parser"` | Filter by filename or title |
| **Custom base dir** | `.\tasks\completed.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Filter`, `-Dbg`

---

## `tasks\cleanup.ps1`

Lists/deletes task files from `.tasks/` folders. Optionally filters by phase number.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\tasks\cleanup.ps1` | Show all task files |
| **Delete all** | `.\tasks\cleanup.ps1 -Force` | Delete after confirmation |
| **Delete phases < N** | `.\tasks\cleanup.ps1 -Force -Phase 60` | Delete only phases before 60 |

**Parameters:** `-BaseDir`, `-Force`, `-Phase` (delete phases < N), `-Dbg`

---

## `tasks\latest-phase.ps1`

Returns the highest phase number found in `.tasks/` folders. Outputs only the number (for scripting).

| Mode | Command | Description |
|------|---------|-------------|
| **Get latest** | `.\tasks\latest-phase.ps1` | Outputs phase number only |
| **With debug** | `.\tasks\latest-phase.ps1 -Dbg` | Shows all found phases |
| **Custom base dir** | `.\tasks\latest-phase.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Dbg`
