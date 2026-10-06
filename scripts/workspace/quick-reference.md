# Quick Reference — Workspace Scripts

Listing and counting what is in the workspace, per-project structure files, and cleanup of caches
and empty folders.

> **Bash invocation:** Prefix with `powershell -File`, use forward slashes, quote paths. See [../quick-reference.md](../quick-reference.md) for full details.
>
> **Base path:** `d:/datrix/datrix/scripts/`

---

## Listing and Counting

### `workspace\projects.ps1`

Lists Datrix project directories and subfolders.

| Mode | Command | Description |
|------|---------|-------------|
| **Project names** | `.\workspace\projects.ps1` | List all project directory names |
| **Src paths** | `.\workspace\projects.ps1 -Src` | Full path to each project's src/ |
| **Tests paths** | `.\workspace\projects.ps1 -Tests` | Full path to each project's tests/ |
| **Docs paths** | `.\workspace\projects.ps1 -Docs` | Full path to each project's docs/ |

**Parameters:** `-Src`, `-Tests`, `-Docs`

### `workspace\project-structure.ps1`

Generates `.project-structure.md` files containing annotated ASCII directory trees (src/, tests/, templates/) for specified projects.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\workspace\project-structure.ps1 datrix-codegen-typescript` | Generate for one project |
| **Multiple projects** | `.\workspace\project-structure.ps1 datrix-codegen-typescript datrix-codegen-python` | Generate for several |
| **All projects** | `.\workspace\project-structure.ps1 -All` | All projects with src/ or tests/ |
| **Custom depth** | `.\workspace\project-structure.ps1 datrix-codegen-typescript -Depth 6` | Deeper tree traversal |
| **Debug** | `.\workspace\project-structure.ps1 datrix-codegen-typescript -Dbg` | Debug logging |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Depth` (default: 4), `-Dbg`

**Output:** Writes `.project-structure.md` to each project's root directory. File is gitignored.

### `workspace\datrix-count.ps1`

Counts `.dtrx` and `.dtrx.false` files across all datrix project directories.

| Mode | Command |
|------|---------|
| **Count** | `.\workspace\datrix-count.ps1` |

**Parameters:** (none)

### `workspace\file-count.ps1`

Counts files with a specified extension across all datrix project directories.

| Mode | Command | Description |
|------|---------|-------------|
| **Default (.j2)** | `.\workspace\file-count.ps1` | Count Jinja2 template files |
| **Python files** | `.\workspace\file-count.ps1 py` | Count .py files |
| **Any extension** | `.\workspace\file-count.ps1 exe` | Count .exe files |

**Parameters:** `-Extension` (positional, default: j2)

---

## Cleanup

### `workspace\cleanup-temps.ps1`

Lists/deletes temporary cache folders and files across the monorepo (`.pytest_cache`, `__pycache__`, `.mypy_cache`, `.ruff_cache`, `.coverage`, etc.).

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\workspace\cleanup-temps.ps1` | Show cache items with sizes |
| **Delete** | `.\workspace\cleanup-temps.ps1 -Force` | Delete after confirmation |
| **Extra folders** | `.\workspace\cleanup-temps.ps1 -Force -AdditionalFolders ".coverage","__pycache__"` | Add extra folder names |
| **Custom base** | `.\workspace\cleanup-temps.ps1 -BaseDir D:\other` | Different workspace |

**Parameters:** `-BaseDir`, `-Force`, `-AdditionalFolders`, `-Dbg`

### `workspace\empty-folders.ps1`

Finds and lists all empty folders recursively from a given path.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\workspace\empty-folders.ps1` | Find empty folders in current dir |
| **Custom path** | `.\workspace\empty-folders.ps1 -Path D:\datrix` | Specific directory |
| **Delete** | `.\workspace\empty-folders.ps1 -Force` | Delete after confirmation |
| **Delete at path** | `.\workspace\empty-folders.ps1 -Path D:\datrix -Force` | Delete at specific path |

**Parameters:** `-Path` (default: current directory), `-Force`, `-Dbg`
