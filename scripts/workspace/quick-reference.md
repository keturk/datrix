# Quick Reference — Workspace Scripts

Bash: prefix `powershell -File`, forward slashes, quoted path ([../quick-reference.md](../quick-reference.md)). Base path `d:/datrix/datrix/scripts/`. What each script does, its module and POSIX twin: [README.md](README.md).

## `workspace\projects.ps1`

List Datrix project directories and subfolders.

| Form | Command |
|------|---------|
| Project names | `.\workspace\projects.ps1` |
| `src/` paths | `.\workspace\projects.ps1 -Src` |
| `tests/` paths | `.\workspace\projects.ps1 -Tests` |
| `docs/` paths | `.\workspace\projects.ps1 -Docs` |

Parameters: `-Src`, `-Tests`, `-Docs`, `-SelfTest`

## `workspace\project-structure.ps1`

Write `.project-structure.md` (annotated tree of src/, tests/, templates/) into each project root.

| Form | Command |
|------|---------|
| One project | `.\workspace\project-structure.ps1 datrix-codegen-typescript` |
| Several | `.\workspace\project-structure.ps1 datrix-codegen-typescript datrix-codegen-python` |
| All with src/ or tests/ | `.\workspace\project-structure.ps1 -All` |
| Deeper tree | `.\workspace\project-structure.ps1 datrix-codegen-typescript -Depth 6` |

Parameters: `-Projects` (positional, variadic), `-All`, `-Depth` (default 4), `-Dbg`, `-SelfTest`

## `workspace\file-count.ps1`

Count files per extension across the datrix projects, one column per extension.

| Form | Command |
|------|---------|
| `.j2` (default) | `.\workspace\file-count.ps1` |
| `.py` | `.\workspace\file-count.ps1 py` |
| `.dtrx` and `.dtrx.false` | `.\workspace\file-count.ps1 -Extension dtrx,dtrx.false` |

Parameters: `-Extension` (positional, comma-separated; default `j2`), `-SelfTest`

## `workspace\cleanup-temps.ps1`

List or delete cache folders and files across the monorepo (`.pytest_cache`, `__pycache__`, `.mypy_cache`, `.ruff_cache`, `.coverage`).

| Form | Command |
|------|---------|
| List (dry run) | `.\workspace\cleanup-temps.ps1` |
| Delete after confirmation | `.\workspace\cleanup-temps.ps1 -Force` |
| Extra folder names | `.\workspace\cleanup-temps.ps1 -Force -AdditionalFolders ".coverage","__pycache__"` |
| Other workspace | `.\workspace\cleanup-temps.ps1 -BaseDir D:\other` |

Parameters: `-BaseDir`, `-Force`, `-AdditionalFolders`, `-Dbg`, `-SelfTest`

## `workspace\empty-folders.ps1`

List or delete empty folders under a path.

| Form | Command |
|------|---------|
| List (dry run) | `.\workspace\empty-folders.ps1` |
| Other path | `.\workspace\empty-folders.ps1 -Path D:\datrix` |
| Delete after confirmation | `.\workspace\empty-folders.ps1 -Force` |
| Delete at path | `.\workspace\empty-folders.ps1 -Path D:\datrix -Force` |

Parameters: `-Path` (default current directory), `-Force`, `-Dbg`, `-SelfTest`
