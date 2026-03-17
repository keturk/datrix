# Bowler codemods for Datrix codebase

AST-based refactors for the **Datrix Python code** (datrix-language, datrix-common, datrix-common, etc.) using [Bowler](https://pybowler.io/) and [libCST](https://libcst.readthedocs.io/).

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/dev/run-codemod.ps1" <args>`. See [scripts/README.md](../../README.md#bash-shell-invocation) for details.

## Setup

Install Bowler in the Datrix venv (it depends on libCST):

```bash
pip install bowler
```

The **run-codemod.ps1** wrapper activates the venv and runs the selected codemod via **run_codemod.py** (in `scripts/library/dev/`).

## Running codemods

From **scripts/dev** (or pass paths from repo root):

```powershell
# Preview (diff only) – rename function
.\run-codemod.ps1 01_rename_function OLD_NAME NEW_NAME
.\run-codemod.ps1 01_rename_function parse_file parse_path datrix-language\src

# Rename class
.\run-codemod.ps1 02_rename_class TreeSitterParser DatrixParser datrix-language\src

# Update imports when module is renamed
.\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src

# Replace print with logger.info (fix logging consistency)
.\run-codemod.ps1 13_print_to_logger datrix-cli\src
```

- **Preview (diff only):** Default; no files are changed.
- **Interactive (apply hunks):** Edit the codemod script: change `.diff()` to `.idiff()`.
- **Apply all:** Change `.diff()` to `.write()` in the codemod script.

**Paths:** If you omit paths, the codemod uses the current directory. Pass one or more dirs or files as the last arguments.

## Scripts

### Basic renames and arguments

| Script | Purpose |
|--------|--------|
| `01_rename_function.py` | Rename a function (definition, calls, imports). `-- OLD_NAME NEW_NAME` |
| `02_rename_class.py` | Rename a class (definition, subclasses, instantiations, imports). `-- OLD_NAME NEW_NAME` |
| `03_add_function_argument.py` | Add a parameter and update callers with default. `-- FUNC_NAME ARG_NAME DEFAULT_VALUE` |
| `04_rename_variable.py` | Rename a variable/constant. `-- OLD_NAME NEW_NAME` |
| `05_custom_modifier.py` | Add `logger = logging.getLogger(__name__)` in modules that lack it. |
| `06_remove_function_argument.py` | Remove a parameter from function and all call sites. `-- FUNC_NAME ARG_NAME` |
| `07_add_decorator.py` | Add a decorator to functions with a given name. Edit DECORATOR_* in script. `-- FUNC_NAME` |
| `08_rename_module_imports.py` | Update imports when a module is renamed. `-- OLD_MODULE NEW_MODULE` |

### Structural and domain-specific

| Script | Purpose |
|--------|--------|
| `09_replace_return_none_with_raise.py` | Replace `return None` with `raise EntityNotFoundError(...)`. Edit ERROR_*, FUNC_NAME_PATTERN. |
| `10_add_return_type_annotation.py` | Add `-> None` (or other type) where missing. Edit RETURN_ANNOTATION. |
| `11_filter_by_filename.py` | Rename a function only in files matching a regex. Edit INCLUDE/EXCLUDE. `-- OLD NEW` |
| `12_replace_raise_exception.py` | Replace `raise Exception(...)` with a specific type and add import. Edit ERROR_MODULE, ERROR_CLASS. |
| `13_print_to_logger.py` | Replace `print(...)` with `logger.info(...)`; add `import logging` and `logger = logging.getLogger(__name__)` when missing. Use for consistent Datrix logging. |

Edit each script to change defaults or constants, then run via `.\run-codemod.ps1 CODEMOD_NAME ...`.

## Implementation

- **PowerShell:** `scripts/dev/run-codemod.ps1` – Activates venv, passes codemod name and args to the Python runner.
- **Python:** `scripts/library/dev/run_codemod.py` – Resolves `scripts/dev/codemods/`, runs `python -m bowler run <script> -- <args>`.

## Tips

- Always run with **diff first** (default) before switching to `.idiff()` or `.write()`.
- Restrict paths to the packages you care about (e.g. `datrix-language\src`) to avoid editing generated or third-party code.
