# Bowler codemods for Datrix codebase

AST-based refactors for the **Datrix Python code** (datrix-language, datrix-common, etc.) using [Bowler](https://pybowler.io/) and [libCST](https://libcst.readthedocs.io/), plus `split-module.ps1`, which splits a large module into siblings and rewrites every importer.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/codemods/run-codemod.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Setup

Install Bowler in the Datrix venv (it depends on libCST):

```bash
pip install bowler
```

The **run-codemod.ps1** wrapper activates the venv and runs the selected codemod via **lib/run_codemod.py**, which finds the numbered recipe beside it in `lib/`.

## `codemods\run-codemod.ps1`

Runs a Bowler codemod from `scripts/codemods/lib/`. All arguments after the codemod name are passed through.

| Mode | Command | Description |
|------|---------|-------------|
| **Rename function** | `.\codemods\run-codemod.ps1 01_rename_function parse_file parse_path` | Preview diff |
| **Rename class** | `.\codemods\run-codemod.ps1 02_rename_class TreeSitterParser DatrixParser datrix-language\src` | Rename in path |
| **Rename imports** | `.\codemods\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src` | Update imports |
| **Print to logger** | `.\codemods\run-codemod.ps1 13_print_to_logger datrix-cli\src` | Replace `print` with `logger.info` |

**Parameters:** `-CodemodName` (positional 0, required), `-CodemodArgs` (positional, variadic)

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

Edit each script to change defaults or constants, then run via `.\codemods\run-codemod.ps1 CODEMOD_NAME ...`.

## `codemods\split-module.ps1`

Splits a large module into sibling modules and points every importer at the new homes. It is not
a Bowler recipe; it runs `lib/split_module.py`. Top-level definitions move **verbatim**, with the
comments above them, so a split cannot change behaviour by re-rendering code. A JSON plan (keep it
under `D:\datrix\.tmp\`) names, for each new module, its docstring and the definitions it
receives:

```json
{
  "_plan_sizing": {"doc": "App Service Plan SKU policy.", "range": ["SKU_MAP", "derive_size"]},
  "_plan_checks": {"doc": "SKU validation.", "names": ["validate_sku", "_tier_of"]}
}
```

`range` claims a contiguous run in source order and `names` an explicit list. `doc` is required, so
no new module inherits the original's docstring. Each new module gets the original's imports, the
imports of what it uses from its siblings, and the original's module-level `pytestmark`. Unclaimed
definitions stay in the original.

**One import path per symbol:** the original does not re-export what moved. Instead, every
`from <original> import <moved name>` in the workspace (`datrix_scripts.import_sites`: every repo's
`src/`, `tests/` and root `*.py`, the scripts tree, the hooks) is rewritten to the new home,
relative imports included, and an inline comment is kept. Then `ruff` (F401, I001) tidies the
imports of the new modules and the original.

The split **refuses and writes nothing** when it would be wrong or incomplete:

- a double claim, an unknown name, a reversed range, or a claimed `pytestmark`;
- an import cycle between the new modules;
- moved code that uses a name left behind (the original imports the new modules, so the reverse import would cycle);
- an `__all__` naming a moved name;
- a module-object read `alias.<moved name>`;
- an import sharing its line with other code;
- the dotted path `<original>.<moved name>` (or `<original>:<moved name>`) written as text in a source file or `pyproject.toml`.

| Mode | Command | Description |
|------|---------|-------------|
| **Preview** | `.\codemods\split-module.ps1 -Module <file.py> -Plan D:\datrix\.tmp\split-plan.json -DryRun` | New modules, remainder, every importer rewrite, every blocker; writes nothing |
| **Split** | `.\codemods\split-module.ps1 -Module <file.py> -Plan D:\datrix\.tmp\split-plan.json` | Write the new modules, the remainder and the importer rewrites |
| **Test module** | `.\codemods\split-module.ps1 -Module <tests\...\test_big.py> -Plan <plan> -PackageModule tests.unit.generators` | A module outside `src/` names its dotted package |

**Parameters:** `-Module <path>` (required), `-Plan <path>` (required), `-PackageModule <dotted>` (required outside a `src/` tree), `-DryRun`. **Exit codes:** 0 = split done (or a clean dry run), 1 = refused (every reason printed), 2 = usage. Run the moved code's tests afterwards (`test.ps1 <pkg> -Specific` / `-Tag`).

## Implementation

- **PowerShell:** `scripts/codemods/run-codemod.ps1` – Activates venv, passes codemod name and args to the Python runner.
- **Python:** `scripts/codemods/lib/run_codemod.py` – Finds the recipe in its own folder, runs `python -m bowler run <script> -- <args>`.
- **Module split:** `scripts/codemods/split-module.ps1` → `scripts/codemods/lib/split_module.py` (not a numbered recipe, so `run-codemod.ps1` never lists it).

## Tips

- Always run with **diff first** (default) before switching to `.idiff()` or `.write()`.
- Restrict paths to the packages you care about (e.g. `datrix-language\src`) to avoid editing generated or third-party code.
