# Workspace Scripts

Listing and counting what is in the workspace, per-project structure files, and cleanup of caches
and empty folders. The commands and parameters of each script are in [quick-reference.md](quick-reference.md);
this file holds what they do and how they are built.

Every wrapper is rendered from `common/templates/entrypoint.ps1`; its behaviour is the
`datrix_scripts.workspace.*` module named below, run in the shared venv. Each has a POSIX twin
`workspace/<name>.sh` taking the module's own flags, each parameter as `--kebab-name`.
`-SelfTest` (`--self-test`) runs the module's self-test and nothing else.

## Listing and Counting

### `projects.ps1`

Lists Datrix project directories and subfolders. `-SelfTest` lists nothing.

Module: `datrix_scripts.workspace.projects`. POSIX twin `projects.sh` (`--src`, `--tests`, `--docs`,
`--self-test`): `bash workspace/projects.sh --src`.

### `project-structure.ps1`

Generates `.project-structure.md` files containing annotated ASCII directory trees (src/, tests/,
templates/) for the specified projects. `-All` covers every project with src/ or tests/. Each file is
written to the project's root directory and is gitignored. `-SelfTest` writes no structure file.

Module: `datrix_scripts.workspace.project_structure`. POSIX twin `project-structure.sh` (`--projects` or
the project positionals, `--all`, `--depth`, `--dbg`, `--self-test`):
`bash workspace/project-structure.sh datrix-codegen-typescript --depth 6`.

### `file-count.ps1`

Counts files by extension across all datrix project directories, one column per extension. A file
counts under an extension only when its name ends with it (`x.dtrx.false` is `dtrx.false`, never
`dtrx`). `-SelfTest` counts nothing.

Module: `datrix_scripts.workspace.file_count`. POSIX twin `file-count.sh` (`--extension` or the extension
positionals, `--self-test`): `bash workspace/file-count.sh --extension dtrx,dtrx.false`.

## Cleanup

### `cleanup-temps.ps1`

Lists or deletes temporary cache folders and files across the monorepo (`.pytest_cache`,
`__pycache__`, `.mypy_cache`, `.ruff_cache`, `.coverage`, etc.). The default is a dry run showing the
items with sizes; `-Force` deletes after confirmation. `-SelfTest` deletes nothing.

Deletion is confined to `-BaseDir`: an item outside it, or reached through a link, is never deleted,
and an `-AdditionalFolders` value that is a path is a usage error.

Module: `datrix_scripts.workspace.cleanup_temps`. POSIX twin `cleanup-temps.sh` (`--base-dir`, `--force`,
`--additional-folders`, `--dbg`, `--self-test`): `bash workspace/cleanup-temps.sh --base-dir D:/other`.

### `empty-folders.ps1`

Finds and lists all empty folders recursively from a given path; `-Force` deletes them after
confirmation. `-SelfTest` deletes nothing.

Deletion is confined to `-Path`: it removes only empty folders, never follows a link, and touches
nothing outside `-Path`.

Module: `datrix_scripts.workspace.empty_folders`. POSIX twin `empty-folders.sh` (`--path`, `--force`,
`--dbg`, `--self-test`): `bash workspace/empty-folders.sh --path D:/datrix`.
