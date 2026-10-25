# Bowler codemods for Datrix codebase

AST-based refactors for the **Datrix Python code** (datrix-language, datrix-common, etc.) using [Bowler](https://pybowler.io/) and [libCST](https://libcst.readthedocs.io/), plus `split-module.ps1`, which splits a large module into siblings and rewrites every importer.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/codemods/run-codemod.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Setup

Bowler and libCST are declared in the `scripts` dependency group of `datrix/pyproject.toml`, which the
shared venv installs (`scripts/common/venv.ps1 -EnsurePackages`, which `test.ps1` runs),
so a venv built from the manifests carries them. Do not `pip install` them by hand: an undeclared
tool is gone after the next rebuild, and `shared-library-gate.ps1 -Only check_scripts_tree` refuses a
scripts-tree import no manifest declares.

The **run-codemod.ps1** wrapper (rendered from `common/templates/entrypoint.ps1`) runs `datrix_scripts.codemods.run_codemod` in the shared venv, which finds the numbered recipe in `scripts/codemods/lib/` and runs it under Bowler. Both wrappers here have a POSIX twin (`run-codemod.sh`, `split-module.sh`) taking the module's own flags, and a `-SelfTest` that runs the module's self-test (including the wrapper seam) and nothing else.

## `codemods\run-codemod.ps1`

Runs a Bowler codemod from `scripts/codemods/lib/`. All arguments after the codemod name are passed through.

| Mode | Command | Description |
|------|---------|-------------|
| **Rename function** | `.\codemods\run-codemod.ps1 01_rename_function parse_file parse_path` | Preview diff |
| **Rename class** | `.\codemods\run-codemod.ps1 02_rename_class TreeSitterParser DatrixParser datrix-language\src` | Rename in path |
| **Rename imports** | `.\codemods\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src` | Preview the import updates (dotted submodules included) |
| **Write** | `.\codemods\run-codemod.ps1 08_rename_module_imports datrix_language.parser datrix_language.parsing datrix-language\src -Write` | Write the previewed rewrite |
| **Print to logger** | `.\codemods\run-codemod.ps1 13_print_to_logger datrix-cli\src` | Replace `print` with `logger.info` |

**Parameters:** `-CodemodName` (positional 0, required), `-CodemodArgs` (positional, variadic), `-Write`, `-SelfTest` (a planted rename previewed, then written; the refusals; the wrapper seam). Only a numbered recipe (`NN_name`) in `scripts/codemods/lib/` runs: any other name, or one holding a path, is refused with the list of recipes (exit 1).

**Module:** `datrix_scripts.codemods.run_codemod`; POSIX twin `codemods/run-codemod.sh` (the recipe and its arguments as positionals, or `--codemod-name` / `--codemod-args`; `--write`) — `bash codemods/run-codemod.sh 01_rename_function parse_file parse_path`.

- **Preview (diff only):** Default; no files are changed.
- **Write:** `-Write` sets `DATRIX_CODEMOD_WRITE=1`; every recipe ends in `finish(query)` (`lib/_shared.py`), which then calls `.write()` instead of `.diff()`. A new recipe ends in `finish(...)` too. The runner puts `lib/` first on `PYTHONPATH`, so a recipe imports its helpers with `from _shared import ...`.
- **`08_rename_module_imports` rewrites import statements only** (`import old`, `from old[.sub] import x`). A module bound by `import old` and used as `old.x` in the body, and a dotted path written as a string (an entry point, a `pyproject.toml` key, a lazy import), keep the old name: finish a rename with a text search for the old name that must come back empty.

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
a Bowler recipe; it runs `datrix_scripts.codemods.split_module`. Top-level definitions move **verbatim**, with the
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
imports of what it uses from its siblings and from the original, and the original's module-level `pytestmark`. Unclaimed
definitions stay in the original.

**One import path per symbol:** the original does not re-export what moved. Instead, every
`from <original> import <moved name>` in the workspace (`datrix_scripts.import_sites`: every repo's
`src/`, `tests/` and root `*.py`, the scripts tree, the hooks) is rewritten to the new home,
relative imports included, and an inline comment is kept. Then `ruff` (F401, I001) tidies the
imports of the new modules and the original.

The split **refuses and writes nothing** when it would be wrong or incomplete:

- a double claim, an unknown name, a reversed range, or a claimed `pytestmark`;
- an import cycle among the new modules and the original. Moved code imports what stays from the original, and the original imports the moved names it still uses, so moved code may use what stays only when nothing that stays uses it back. The refusal names the cycle and the names on each edge: claim those into the same module;
- an `__all__` naming a moved name;
- a module-object read `alias.<moved name>`;
- an import sharing its line with other code.

A dotted path `<original>.<moved name>` (or `<original>:<moved name>`) written as text in any `src/` file or
`pyproject.toml` (a docstring cross-reference, a `.dal` adapter path) is rewritten to the new module, byte for
byte so line endings stay.

| Mode | Command | Description |
|------|---------|-------------|
| **Preview** | `.\codemods\split-module.ps1 -Module <file.py> -Plan D:\datrix\.tmp\split-plan.json -DryRun` | New modules, remainder, every importer rewrite, every blocker; writes nothing |
| **Split** | `.\codemods\split-module.ps1 -Module <file.py> -Plan D:\datrix\.tmp\split-plan.json` | Write the new modules, the remainder and the importer rewrites |
| **Test module** | `.\codemods\split-module.ps1 -Module <tests\...\test_big.py> -Plan <plan> -PackageModule tests.unit.generators` | A module outside `src/` names its dotted package |

**Parameters:** `-Module <path>` (required), `-Plan <path>` (required), `-PackageModule <dotted>` (required outside a `src/` tree), `-DryRun`, `-SelfTest` (a planted workspace: a dry run, a split with its importer rewritten, moved code importing what stays, a cycle refused, a refused plan). **Exit codes:** 0 = split done (or a clean dry run), 1 = refused (every reason printed), 2 = usage. Run the moved code's tests afterwards (`test.ps1 <pkg> -Specific` / `-Tag`).

**Module:** `datrix_scripts.codemods.split_module`; POSIX twin `codemods/split-module.sh` (`--module`, `--plan`, `--package-module`, `--dry-run`, `--self-test`).

## Implementation

- **Wrappers:** `scripts/codemods/run-codemod.ps1` and `split-module.ps1` (and their `.sh` twins), rendered from `common/templates/entrypoint.ps1`.
- **Runner:** `datrix_scripts.codemods.run_codemod` (in `scripts/common/lib/`) – finds the recipe in `scripts/codemods/lib/`, runs `python -m bowler run <script> -- <args>`.
- **Module split:** `datrix_scripts.codemods.split_module` (not a numbered recipe, so `run-codemod.ps1` never lists it).
- **Recipes:** `scripts/codemods/lib/NN_*.py` (and their shared helpers `_shared.py`): files Bowler loads by path, not importable modules.

## Tips

- Always run with **diff first** (default) before `-Write`.
- Restrict paths to the packages you care about (e.g. `datrix-language\src`) to avoid editing generated or third-party code.
