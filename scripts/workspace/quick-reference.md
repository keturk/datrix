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

**Parameters:** `-Src`, `-Tests`, `-Docs`, `-SelfTest` (runs the module's self-test and lists nothing)

**Module:** `datrix_scripts.workspace.projects`; POSIX twin `workspace\projects.sh` (`--src`, `--tests`, `--docs`, `--self-test`) — `bash workspace/projects.sh --src`.

### `workspace\project-structure.ps1`

Generates `.project-structure.md` files containing annotated ASCII directory trees (src/, tests/, templates/) for specified projects.

| Mode | Command | Description |
|------|---------|-------------|
| **One project** | `.\workspace\project-structure.ps1 datrix-codegen-typescript` | Generate for one project |
| **Multiple projects** | `.\workspace\project-structure.ps1 datrix-codegen-typescript datrix-codegen-python` | Generate for several |
| **All projects** | `.\workspace\project-structure.ps1 -All` | All projects with src/ or tests/ |
| **Custom depth** | `.\workspace\project-structure.ps1 datrix-codegen-typescript -Depth 6` | Deeper tree traversal |
| **Debug** | `.\workspace\project-structure.ps1 datrix-codegen-typescript -Dbg` | Debug logging |

**Parameters:** `-Projects` (positional, variadic), `-All`, `-Depth` (default: 4), `-Dbg`, `-SelfTest` (runs the module's self-test and writes no structure file)

**Module:** `datrix_scripts.workspace.project_structure`; POSIX twin `workspace\project-structure.sh` (`--projects` or the project positionals, `--all`, `--depth`, `--dbg`, `--self-test`) — `bash workspace/project-structure.sh datrix-codegen-typescript --depth 6`.

**Output:** Writes `.project-structure.md` to each project's root directory. File is gitignored.

### `workspace\file-count.ps1`

Counts files by extension across all datrix project directories, one column per extension. A file counts under an extension only when its name ends with it (`x.dtrx.false` is `dtrx.false`, never `dtrx`).

| Mode | Command | Description |
|------|---------|-------------|
| **Default (.j2)** | `.\workspace\file-count.ps1` | Count Jinja2 template files |
| **Python files** | `.\workspace\file-count.ps1 py` | Count .py files |
| **DSL sources** | `.\workspace\file-count.ps1 -Extension dtrx,dtrx.false` | `.dtrx` and disabled `.dtrx.false` files, two columns |

**Parameters:** `-Extension` (positional, one or more, comma-separated; default: j2), `-SelfTest` (runs the module's self-test and counts nothing)

**Module:** `datrix_scripts.workspace.file_count`; POSIX twin `workspace\file-count.sh` (`--extension` or the extension positionals, `--self-test`) — `bash workspace/file-count.sh --extension dtrx,dtrx.false`.

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

**Parameters:** `-BaseDir`, `-Force`, `-AdditionalFolders`, `-Dbg`, `-SelfTest` (runs the module's self-test, deletes nothing)

Deletion is confined to `-BaseDir`: an item outside it, or reached through a link, is never deleted, and an `-AdditionalFolders` value that is a path is a usage error.

**Module:** `datrix_scripts.workspace.cleanup_temps`; POSIX twin `workspace\cleanup-temps.sh` (`--base-dir`, `--force`, `--additional-folders`, `--dbg`, `--self-test`) — `bash workspace/cleanup-temps.sh --base-dir D:/other`.

### `workspace\empty-folders.ps1`

Finds and lists all empty folders recursively from a given path.

| Mode | Command | Description |
|------|---------|-------------|
| **List (dry run)** | `.\workspace\empty-folders.ps1` | Find empty folders in current dir |
| **Custom path** | `.\workspace\empty-folders.ps1 -Path D:\datrix` | Specific directory |
| **Delete** | `.\workspace\empty-folders.ps1 -Force` | Delete after confirmation |
| **Delete at path** | `.\workspace\empty-folders.ps1 -Path D:\datrix -Force` | Delete at specific path |

**Parameters:** `-Path` (default: current directory), `-Force`, `-Dbg`, `-SelfTest` (runs the module's self-test, deletes nothing)

Deletion is confined to `-Path`: it removes only empty folders, never follows a link, and touches nothing outside `-Path`.

**Module:** `datrix_scripts.workspace.empty_folders`; POSIX twin `workspace\empty-folders.sh` (`--path`, `--force`, `--dbg`, `--self-test`) — `bash workspace/empty-folders.sh --path D:/datrix`.
