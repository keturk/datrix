---
model: claude-sonnet-5-5
effort: medium
description: Add a new tool script to d:\datrix\datrix\scripts in a named subfolder that does a given task — a thin PowerShell wrapper rendered from the entrypoint template, its .sh twin, and the Python module under common/lib/datrix_scripts/<subfolder>/ with an argparse entry point and a --self-test, plus its quick-reference section. Use when Jon asks to "add a script", "create a script in <folder> that does X", or runs /add-script <subfolder> <what it should do>.
---

# Add Script

Create one Datrix tool script: **a wrapper in `datrix/scripts/<subfolder>/` and a Python module in
`datrix/scripts/common/lib/datrix_scripts/<subfolder>/`**. The wrapper holds no behaviour; the module
does the work. Gates (`scripts/gates/`, `scripts/test/*-gate.ps1`) have extra rules — for a gate, read
`datrix/scripts/gates/README.md` § How a gate is built before step 3.

**Input:** a subfolder (`workspace`, `dev`, `scan`, `metrics`, `generation`, `git`, `tasks`, …) and what
the script must do. Optional: a name. If the task is ambiguous in a way the code and docs cannot settle,
ask Jon in one line; otherwise choose and carry on. Scripts are called from bash as
`powershell -File "d:/datrix/datrix/scripts/<subfolder>/<name>.ps1"` (forward slashes).

## Step 1: Read (do not act from memory)

1. `datrix/scripts/common/README.md` — § *Where Python lives*, § *Wrappers rendered from the template*, § *Adding a script*.
2. `datrix/scripts/<subfolder>/quick-reference.md` — the folder's scripts and the section format to copy.
3. The nearest sibling in the same subfolder: its `.ps1`, `.sh` and `common/lib/datrix_scripts/<subfolder>/<name>.py`. `workspace/file-count.*` with `workspace/file_count.py` is a complete small model. Copy its shape, not its content.
4. `datrix-common/docs/contributing/ai-agent-rules/code-quality-standards.md` (quick rules at the top). A script that deletes, moves, or runs processes: also `ai-agent-rules/secure-by-default.md`.

## Step 2: Check it does not already exist

Before writing, name the question: *does a script or `datrix_scripts` helper already do this?*

- Grep the folder's `quick-reference.md` and `scripts/quick-reference.md` for the purpose.
- `find_symbol` / `search` (code index) for the helpers you would otherwise write: path discovery (`datrix_scripts.paths`), repo enumeration (`framework_repos.workspace_package_dirs`), comma-list arguments (`dev.arguments.comma_values`), removal and listing (`cleanup_utils`), project selection (`metrics.projects`, `scan.selection`), output colour (`logging_utils`). **One fact, one home**: reuse the helper; never copy its body. `test\shared-library-gate.ps1` refuses a copied helper body.
- If an existing script already does the task, say so and stop; extending it is a different request.

## Step 3: Write the Python module

`common/lib/datrix_scripts/<subfolder>/<name_with_underscores>.py` (wrapper `foo-bar.ps1` ↔ module `foo_bar.py`, module path `datrix_scripts.<subfolder>.foo_bar`). The subfolder package already has an `__init__.py`.

- Module docstring: what it does, how it is run (wrapper name), the exit codes, the usage lines — as `file_count.py` does.
- `MODULE` and `WRAPPER` constants; `build_parser()` returning `argparse.ArgumentParser(prog=WRAPPER, ..., allow_abbrev=False)`. Every wrapper parameter is an option `--kebab-name` (`-SkipIfInstalled` → `--skip-if-installed`); the parser's options and the wrapper's parameters must be the same set. Always `--self-test` (`-SelfTest`). Set `parser.set_defaults(debug=False)` (the runner reads `args.debug`), or if the wrapper declares `-Dbg`, copy how the nearest sibling that declares it spells the option.
- `main(argv=None)` ends in `module_main(parser, dispatch, argv)` from `datrix_scripts.test.wrappers`; the `--self-test` branch returns `run_self_test(checks, wrapper=WRAPPER, module=MODULE, parser=parser, folder=<SUBFOLDER>_SCRIPTS_DIR)` (the folder constants are in `test/wrappers.py`; a new subfolder needs one added there). `if __name__ == "__main__": sys.exit(main())`.
- Exit codes: `EXIT_PASS` 0, a finding or failed self-test 1, usage error 2 (raise `UsageError`); import them from `datrix_scripts.gate_harness`.
- Code standards: full type hints, no `Any`, `from __future__ import annotations`, %-style logging, complexity ≤ 15, no `pass`/TODO/silent fallbacks, `encoding="utf-8"` on every text open. Locations come from `datrix_scripts.paths` — never `Path(__file__).parents[N]`, never `sys.path` edits.
- **Security:** child processes get an argument vector, never a shell string; a script that removes or moves files refuses any target at or above its base, never enters a link, and confirms through `cleanup_utils`; no credential read or written; no input reaches a path or command unvalidated.
- **Self-test = the test.** The `datrix` repo has no test suite and framework tests use real objects. The checks are plain functions (`_check_...`) run against a planted workspace in a `TemporaryDirectory` (`gate_harness.write_files`, `cleanup_utils.plant_directory_link`), proving the behaviour and that each refusal path fires. No mocks.

## Step 4: Write the wrapper and its twin

In `datrix/scripts/<subfolder>/`:

- `<name>.ps1`: shebang, comment-based help (`.SYNOPSIS`, `.DESCRIPTION`, one `.PARAMETER` per parameter, `.EXAMPLE`s), `[CmdletBinding()] param(...)` including `[switch]$SelfTest`, then **the template's tail byte for byte** from `common/templates/entrypoint.ps1`, with `{{MODULE}}` replaced by the module path. Copy the tail from the sibling you read; do not retype it. At most 40 code lines (help comments are free).
- `<name>.sh`: `common/templates/entrypoint.sh` with `module="datrix_scripts.<subfolder>.<name>"` substituted; nothing else changes.

## Step 5: Document it

- `datrix/scripts/<subfolder>/quick-reference.md` is **how to run it, and nothing else**, in the folder's format: a `##`/`###` section `` `<subfolder>\<name>.ps1` ``, a one-line purpose, a Form/Command table, one `Parameters:` line listing exactly the declared ones with defaults, and one `Exit:` line. Agents read this file to learn the invocation, so keep it lean. `script-catalogue-gate` refuses an undocumented script or a documented flag the `param()` block does not declare.
- `datrix/scripts/<subfolder>/README.md` is **what it does**: the same script's section with the prose (why it exists, how it decides, what it records or proves, its self-test, troubleshooting), the `**Module:**` naming `datrix_scripts.<subfolder>.<name>` and the `.sh` twin. The quick-reference links the README from its header; flags written in the README are checked against `param()` like those in the quick-reference.
- `datrix/scripts/quick-reference.md`: add the script name to the folder's row of the Category table.
- `datrix/scripts/common/README.md`: add the module to the folder's row of the `lib/datrix_scripts` table.
- **New subfolder** (Jon named one that does not exist): also create the package `__init__.py`, the `<SUBFOLDER>_SCRIPTS_DIR` constant in `test/wrappers.py`, the folder's `quick-reference.md` and `README.md`, and a new row in the Category table.
- No design or task numbers in any comment or doc (`design-task-reference-gate`).

## Step 6: Verify (static first; these are targeted, not suites)

Run, in order, and report what each printed:

1. `powershell -File "d:/datrix/datrix/scripts/<subfolder>/<name>.ps1" -SelfTest` — all checks `[OK]`, including `wrapper_seam` and `exact_option_spelling`.
2. One real invocation from the quick-reference table, on a small input, and show the output. Never a whole-suite or generation sweep.
3. `powershell -File "d:/datrix/datrix/scripts/gates/repo-hygiene/thin-entrypoint-gate.ps1" -Only scripts_tree`
4. `powershell -File "d:/datrix/datrix/scripts/gates/repo-hygiene/script-catalogue-gate.ps1" -Only scripts_tree`
5. `powershell -File "d:/datrix/datrix/scripts/test/shared-library-gate.ps1" -Only check_scripts_tree`
6. `D:/datrix/.venv/Scripts/python.exe -m ruff check <the new module file>` — only the file you wrote, never `--fix` on a folder.

A red gate that names your files is fixed, not explained. A red gate that names files you did not touch goes into a findings file (`execution-contract-reporting.md` §5A) and you carry on. Do not run `mypy` (waived).

## Step 7: Report

Name the files created (`file:line` links), the self-test and gate results as printed, and the one invocation you ran. Nothing else.

## Anti-patterns

- Putting logic in the `.ps1`, or a Python file beside the wrapper: the gates refuse both.
- Retyping the template tail instead of copying it, or omitting the `.sh` twin.
- A parameter in the wrapper with no matching parser option, or the reverse.
- Copying a helper's body instead of importing it.
- Writing the files through a shell (heredoc, `Set-Content`): use Write/Edit.
- Documenting a flag the script does not declare, leaving the script out of `quick-reference.md`, or putting design prose in `quick-reference.md` instead of the folder's `README.md`.
- Adding a gate module for a parity fact (it is a row in `gates/parity/cases/`).
