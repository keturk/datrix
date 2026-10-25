# Common Modules

Shared PowerShell modules used by all scripts, the wrapper template, the shared venv's wrapper,
and `lib/datrix_scripts/`, the Python package every scripts folder shares.

## Files

| File | Description |
|------|-------------|
| `DatrixPythonScript.psm1` | `Invoke-DatrixEntrypoint`, the body of every wrapper (each is rendered from `templates/entrypoint.ps1`); `Invoke-DatrixPythonScript`, which runs a Python file or module from PowerShell and which no wrapper calls; gate mode, its verdict line and gate logs |
| `DatrixPaths.psm1` | Path discovery for the workspace, the repository directories, the shared venv and its interpreter, and the scripts `PYTHONPATH` |
| `templates/entrypoint.ps1`, `templates/entrypoint.sh` | The wrapper template and its POSIX twin (see [Wrappers rendered from the template](#wrappers-rendered-from-the-template)) |
| `venv.ps1`, `venv.sh` | The shared venv: creation, the architecture check, package installation, the package lock, the CLI check |
| | Module: `datrix_scripts.venv` |
| `venv-install-order.ps1`, `venv-install-order.sh` | Self-test of the package install order |
| | Module: `datrix_scripts.install_order` |
| `venv-dev-specs.ps1`, `venv-dev-specs.sh` | Self-test of the `[dev]` specs and dependency-group specs the venv installs |
| | Module: `datrix_scripts.dev_specs` |
| `DatrixRunLog.psm1` | Run-log file naming and **exclusive** claiming — two runs never share one log file |
| `lib/datrix_scripts/` | The shared Python package (below) |

## Where Python lives

Where a Python file lives follows from what runs or imports it:

- **A wrapper runs it** → `common/lib/datrix_scripts/<category>/<name>.py`, run as the module
  `datrix_scripts.<category>.<name>` by a wrapper rendered from the template (below); a gate family's
  modules sit in `common/lib/datrix_scripts/gates/<family>/`.
- **More than one folder, a hook, or a package test imports it** → `common/lib/datrix_scripts/`,
  always imported as `datrix_scripts.<name>`.
- **Loaded by path** → the one `lib/` folder beside a wrapper is `codemods/lib/`: the numbered Bowler
  recipes `datrix_scripts.codemods.run_codemod` loads by path, whose files import each other by bare
  name (`from _shared import ...`).

`Invoke-DatrixEntrypoint` points the child's environment at the shared venv
(`Enter-DatrixVenvEnvironment`), which puts `scripts\common\lib` first on `PYTHONPATH`, so every
wrapper's Python can import `datrix_scripts`; the caller's environment is restored afterwards. A Python process that starts
another Python process passes `datrix_scripts.paths.script_env()` as its environment. Hooks call
`add_scripts_lib_to_path()` (`claude-config/.claude/hooks/_hook_log.py`), and the MCP servers are
registered with `PYTHONPATH` in their `env` (re-run `dev\code-index.ps1 -Setup`,
`dev\local-llm.ps1 -Setup` and `dev\line-edit.ps1 -Setup` on each machine after a server's module changes).

Never compute a location from `Path(__file__).parents[N]`: import it from `datrix_scripts.paths`
(`SCRIPTS_DIR`, `CONFIG_DIR`, `SHOWCASE_DIR`, `WORKSPACE_DIR`, `lib_script(folder, name)`).

No production script inserts a path into `sys.path`: the venv's editable installs and the
`PYTHONPATH` the runner sets are the only import paths. The only inserts are self-test fixtures
that plant a synthetic distribution or module in a temp directory, and `hook_modules.py` (the hooks directory
is no package).

### One home per fact

Each of these has exactly one home, and `test\shared-library-gate.ps1` holds it with a census that
must report zero (each census first reports a planted copy):

| Fact | Home | Census |
|------|------|--------|
| Check running, `_ok`/`_fail`, logging setup | `datrix_scripts.gate_harness` | no other top-level `run_checks`, `run_self_test_checks`, `harness_self_test`, `_ok`, `_fail`, `configure_logging` |
| Checking the venv and running Python | `datrix_scripts.venv`; `Invoke-DatrixEntrypoint` / `Invoke-DatrixPythonScript` | no `.ps1` calls a retired venv function (`Ensure-DatrixVenv`); every gate wrapper prints the verdict line |
| The workspace root | `Get-DatrixWorkspaceRoot` / `datrix_scripts.paths.WORKSPACE_DIR` | no retired resolver is defined or named |
| Enumerating `datrix-*` directories | `framework_repos.workspace_package_dirs` | no loop over an `iterdir()` tests a `datrix` prefix |
| Import paths | the venv | no `sys.path` mutation outside the fixtures above |
| A helper body | its shared module | no function body of three or more statements is AST-identical across two files; no module-level function of any length copies a public `datrix_scripts` function in another file (docstring, annotations and decorators ignored, the names it binds renamed by position, every free name resolved to the import or definition it denotes; a body that only returns a constant is no home) |
| A gate's self-test | the gate | every gate wrapper declares `-SelfTest` |

One more census of the same gate holds a defect class rather than a home: **unrolled-append**
refuses a `.ps1`/`.psm1` that assigns a variable from a bare `if`, `switch`, loop or `try`
statement and later grows it with `+=` (wrap the statement in `@(...)`, as under *Adding a
script*).

The same gate proves that every `datrix_scripts` module imports as the first import of a fresh
interpreter, and that every module a hook imports is exercised by a gate or carries its own
`self_test` (`consumed − covered` is empty): hooks fail open, so a broken import would silently
disable one.

`test\shared-library-gate.ps1 -Only check_scripts_tree` holds the layout: no `scripts\library`
folder, every Python file in a `lib/` folder, no `lib/` module named like a stdlib or installed
module, every import resolvable, every script a wrapper runs present, and every script path a doc,
skill, hook, config or package file names present.

### Wrappers rendered from the template

Every script's behaviour is a `datrix_scripts.<category>.<script>` module (or a shared module such
as `datrix_scripts.venv`), and its wrapper is written by hand from `templates/entrypoint.ps1`: the
template's `# {{PARAMETER_BLOCK}}` line becomes the wrapper's own
comment-based help and `param()` block, `{{MODULE}}` becomes its module, and every other line is the
template's, byte for byte. The body is `Invoke-DatrixEntrypoint -Module <module> -Parameters
$PSBoundParameters` and `exit $LASTEXITCODE`: each bound parameter is passed as `--kebab-name`
(`-SkipIfInstalled` → `--skip-if-installed`; a value as `--name=<value>`, an array as one
`--name=<value>` per element; PowerShell's common parameters are not passed), in an argument vector,
never a shell string, and the module's exit code is the wrapper's. The module is an `argparse` entry
point whose options are exactly those flags. When the venv has no interpreter yet, the wrapper first
creates it (`python -m datrix_scripts.venv --ensure` under `DATRIX_PYTHON`, else the first of `py`,
`python`, `python3` on `PATH`). The POSIX twin beside the wrapper, `<name>.sh`, is
`templates/entrypoint.sh` with the module substituted; it passes its arguments through unchanged, so
on POSIX the module's own flags are typed (`bash common/venv.sh --help`).

`datrix_scripts.entrypoint.wrapper_problems(wrapper, module, parser)` holds the seam, and every
module with a wrapper calls it from its `--self-test`: the wrapper and its twin are the templates
rendered, and the wrapper's parameters and the parser's options are one set (each first proven on
planted drift).

`gates\repo-hygiene\thin-entrypoint-gate.ps1` holds the whole tree to that form: every `.ps1` under
`datrix/scripts/` except the template is the template rendered, has its `.sh` twin, and carries at
most 40 code lines (lines holding a token other than a comment, read through PowerShell's own
tokenizer, so the comment-based help is free).

#### Moving a script's behaviour into Python

There is no wrapper generator: each wrapper is written by hand from the template, and
`wrapper_problems` is what catches it drifting.

- **The module.** The behaviour becomes `datrix_scripts.<category>.<script>`: an `argparse` entry
  point with the script's parameters as its options, reusing the existing `datrix_scripts` helpers
  (look a helper up with the code index's `find_symbol` before adding one), and a `--self-test` for
  the behaviour it moved. Logic that already sits in a Python file keeps its code; the file moves
  into `datrix_scripts.<category>` (bare sibling imports become `datrix_scripts.<category>.<name>`):
  the template puts only `common/lib` on `PYTHONPATH`.
- **Gate mode.** A gate's `main` is `datrix_scripts.gate_log.run_as_gate`, so the wrapper's run
  keeps its whole output in a claimed log under `.test-output/gates/<gate>/` and ends on the
  `[GATE] <gate> PASSED|FAILED exit=<n> log=<path>` line.
- **Unchanged surface.** Script names, parameters, exit codes and the command parsing of the hooks
  that guard them do not change. The script's `quick-reference.md` section keeps its table, and its
  folder's `README.md` section gains one line naming the module.
- **Proof.** The module's `--self-test` passes, and one documented invocation from the script's
  `quick-reference.md`, run before and after the move, gives the same exit code and output summary. A
  script that runs tests, a generation or a deploy is proven with its `-SelfTest`, `-ListTags` or
  dry-run forms only, never by a whole suite or a generation sweep.
- **No new credential.** Passing the arguments as a vector removes PowerShell interpolation from
  command construction; moving a script gives it no credential it did not already have.

### Adding a script

1. Put the Python in `common/lib/datrix_scripts/<category>/<name>.py`: an `argparse` entry point
   (`allow_abbrev=False`) whose options are the wrapper's parameters, with a `--self-test` that runs
   the wrapper seam checks (`datrix_scripts.test.wrappers.run_self_test` or `seam_checks`). A gate's
   `main` runs in gate mode (above) and its wrapper declares `-SelfTest`.
2. Write the wrapper in the folder it belongs to, rendered from the template (above), and its `.sh`
   twin. `gates\repo-hygiene\thin-entrypoint-gate.ps1` refuses any other form.
3. Add its section to the folder's `quick-reference.md` (the forms, exactly the parameters it declares
   and its exit codes) and to the folder's `README.md` (what it does, how it decides, its module and
   POSIX twin); `gates\repo-hygiene\script-catalogue-gate.ps1` holds both.

## lib/datrix_scripts

| Module | Description |
|--------|-------------|
| `paths.py` | Fixed locations in the scripts tree, the showcase repository and the workspace; `script_env()` |
| `venv.py` | The shared venv (run by `common\venv.ps1`; see [venv.ps1](#venvps1)), and for every script: the venv's interpreter (`get_venv_python`), whether a venv is active, the refusal for a declared tool that does not import (`missing_declared_tool`), and the venv repair command any other refusal names (`venv_repair`) |
| `entrypoint.py` | The seam between a wrapper rendered from `templates/entrypoint.ps1` and its module (`wrapper_problems`), and the wording of a wrapper command in a message (`wrapper_command`: `common\venv.ps1 -Ensure` on Windows, `common/venv.sh --ensure` elsewhere) |
| `install_order.py` | The `datrix-*` package install order for the shared venv (`topological_install_order`) |
| `dev_specs.py` | A package's `[dev]` specs as the shared venv installs them (`installable_dev_specs`): a direct-URL spec to a sibling workspace package becomes its bare name, so pip never replaces that package's editable install with a frozen copy. `read_dependency_group` reads a PEP 735 dependency group's specs (`include-group` expanded; a missing group, a cycle or a malformed entry is refused): the venv reads the `scripts` group of `datrix/pyproject.toml` this way |
| `framework_repos.py` | The framework git repositories at the workspace root, discovered, never listed; `workspace_package_dirs(workspace, any_of=…, include_showcase=…)` is the only enumeration of `datrix-*` directories (filtered by `PackageMarker`: `src`, `tests`, `pyproject.toml`, `package.json`, `.git`), and each caller keeps its own keying |
| `gate_harness.py` | The one check loop every gate runs, its non-vacuity proof, `[OK]`/`[FAIL]` printing, logging setup, the shared gate flags and the planted-fixture writer (see [../gates/README.md](../gates/README.md#how-a-gate-is-built)) |
| `gate_log.py` | Gate mode for a gate behind a rendered wrapper (`run_as_gate`): the claimed gate log, the relayed output, and the verdict line the red-run digest hook reads |
| `run_log.py` | Run-log naming and **exclusive** claiming (`O_CREAT \| O_EXCL`), the Python twin of `DatrixRunLog.psm1`; `test\run-log-exclusivity-gate.ps1` holds both to one naming |
| `count_ratchet.py` | The two count-ratchet semantics (tighten-only, exact-pin) and the fail-closed count-table reader and writers |
| `powershell_ast.py` | Parameters, calls, definitions, flow-control-statement assignments, `+=` targets and code-line counts (`code_lines`: lines holding a token other than a comment) of PowerShell scripts, read through PowerShell's own parser in one child process |
| `hook_modules.py` | Loads a harness hook module by path, so a gate shares the hook's one definition instead of a copy |
| `registered_targets.py` | The registered `datrix.languages` / `datrix.platforms` targets and their `src/` directories -- the one place a script learns which targets exist |
| `pyproject_deps.py` | `datrix-*` dependency declarations read from `pyproject.toml` |
| `capped_log.py` | Append-only logs with a size cap (hooks and scripts share it) |
| `logging_utils.py` | Logging and tee-style output (console + file); `TeeLogger` claims a run directory exclusively |
| `test_projects.py` | Project discovery from `config/test-projects.json` |
| `test_project.py` | The per-package test runner; `test\test.ps1` runs one `test_project` child per package |
| `test/` | The modules behind the `scripts/test/` wrappers rendered from the template: `test.py` (`test\test.ps1`: project selection, the install check through `venv.require_packages`, one child per package, the summary, digests, `-ListTags`), `test_single.py`, `cases.py`, `tables.py`, `model_contracts.py`, `status_unit_tests.py`, `status_deploy_tests.py`, `extract_warnings.py`, `cleanup.py`, `run_complete.py` (`test\run-complete.ps1`: the request checks, the workflow steps, the rerun loop) with `run_complete_rerun.py` (which projects a `-Rerun` selects), `dual_target.py`, `tag_vocabulary.py` (the tags a package's tests use and the ones missing from the vocabulary table), `compare_tests.py`, `mypy_check.py`, `gate_verdict.py`, `affected_gate.py`, `retag.py` (`test\retag.ps1`: feature-tag renames across every tag carrier), the test-tooling gates (`shared_library_gate.py` with `scripts_contract_checks.py`, `scripts_tree_census.py` and `run_complete_checks.py`; `runner_plugin_gate.py`, `test_tooling_parsing_gate.py` with `post_process_test_results.py`, `test_specific_selection_gate.py`, `run_log_exclusivity_gate.py`, `toolchain_free_suites.py`), and `wrappers.py` (their shared self-test loop and `main`, the wrapper seam checks, UTF-8 output and the `-Command` wrapper options) |
| `tasks/` | The modules behind the `scripts/tasks/` wrappers rendered from the template: `todo.py` and `completed.py` with their shared scan `task_listing.py`, `complete.py` (the one way a task heading becomes `COMPLETED:`), `cleanup.py`, `latest_phase.py`, the phase analyses `phase_status.py`, `plan_waves.py`, `plan_waves_multi.py` and `validate_dependencies.py` with their shared phase arguments and planted phases `phase_cli.py`, `validate_task.py` with `task_citations.py`, `retrofit_orientation.py`, and the gate `task_orientation_gate.py`; the task-file parsing they read is `task_metadata.py` and `task_orientation.py` |
| `dev/` | The modules behind the `scripts/dev/` wrappers rendered from the template (each also uses `datrix_scripts.test.wrappers`): `generate.py` (`dev\generate.ps1`: the install, plugin and `datrix` command checks, the claimed run log, the output filter and summary) with `generate_projects.py` (one `datrix generate` per project, output paths from `config/test-projects.json`), `generate_doc_fragments.py`, `find_imports.py`, `who_imports.py`, `print_sexp.py`, `check_docs.py`, `code_index.py` with its MCP server `code_index_mcp.py`, `logic_map_report.py`, `local_llm.py` with its MCP server `local_llm_mcp.py`, `line_edit.py` with its MCP server `line_edit_mcp.py`, `mcp_setup.py` (the `-Setup` of all three: the `.mcp.json` entry and the machine's approval), `ineedtoknow.py`, `code_scan.py`, `generate_test_rules.py`, the gates `code_index_gate.py`, `local_llm_gate.py`, `line_edit_gate.py` and `ineedtoknow_gate.py`, and `arguments.py` (how a module reads the comma-joined values its wrapper passes) |
| `generation/` | The modules behind the `scripts/generation/` wrappers rendered from the template: `rebuild_parser.py`, `refresh_example_snapshot.py`, `refresh_seed_datasets.py`, `status_generation.py`, `triage_failures.py`, `compare_generated.py`, `tree_hash.py`, `evaluate_generated_scan.py`, `evaluate_service_scan.py`, `evaluate_services.py` with `service_triage.py` (run as one child per service), and `delete_generated.py` (the rename, the containment checks and the detached removal) |
| `visualize/` | The modules behind the `scripts/visualize/` wrappers rendered from the template: `visualize.py`, `openapi_gen.py`, `schema_snapshot.py`, `schema_diff.py`, `status_docs.py`, `all_reports.py` (runs the first, second and fifth as child modules), and `projects.py` (their shared project selection: `-Source` or a test set, and the planted example of their self-tests); the loading and builders they call are `visualization/` |
| `metrics/` | The modules behind the `scripts/metrics/` wrappers rendered from the template (`complexity.py`, `duplicate.py` and `dead_code_report.py` also hold the checks `dev\code-scan.ps1` imports; `call_count.py` counts calls during one in-process workload), and `projects.py` (their shared `-Projects`/`-All` selection, per-project loop and summary) |
| `workspace/` | The modules behind the `scripts/workspace/` wrappers rendered from the template: `projects.py`, `project_structure.py`, `file_count.py`, and the deleting `cleanup_temps.py` and `empty_folders.py` (their removals never enter a link and never reach at or above the base folder, proven in each `--self-test`) |
| `scan/` | The modules behind the `scripts/scan/` wrappers rendered from the template, one `<wrapper stem>.py` each (`compile.py`, which also checks any path's containing package, `syntax_checker.py`, `config_linter.py`, `datrix_linter.py`, `datrix_format.py`, `libcst.py`, `semgrep.py`, `ast_grep.py`, `check_debug_artifacts.py`, `check_python_bytecode.py`, `extra_parens.py`, `ruff_checker.py`, `audit.py`, `dgen_census.py`, `find_duplicate_bodies.py`, `find_unimplemented_abstracts.py`, `check_import_boundaries.py`); `selection.py` (their shared target selection: paths or projects, or `--all`, the usage and the both-given refusal, and the comma split of a list value); and the `import_boundaries` package (the boundary rule model, the scanners and the ratchets `check_import_boundaries.py` runs; `python -m datrix_scripts.scan.import_boundaries` runs the scan alone) |
| `codemods/` | The modules behind the `scripts/codemods/` wrappers: `run_codemod.py` (runs a numbered Bowler recipe from `scripts/codemods/lib/`, which stays there because Bowler loads recipes by path), `split_module.py` and `rewrite.py` (Ruff's UP, FURB and PERF fixes over one or more projects) |
| `review/` | The task review system behind the `scripts/review/` wrappers: `review.py` (the orchestrator; its wrapper passes every argument through), `review_reply.py`, `review_schema.py`, `canonical_modules.py`, `escalation.py`, `tier2_local.py`, `apply_reviews_prep.py`, and the gate `review_library_gate.py` |
| `skill/` | The modules behind the `scripts/skill/` wrappers rendered from the template: the headless skill chains `implement_design.py`, `implement_finding.py`, `organize_findings.py` and `skill_chain.py` over their shared step runner `chain.py` (the prompt on stdin, argument validation, the kept and shown stream, the summary table, the verify and absorb steps); the skill assists `skill_assist.py` with its command line `assist_cli.py` and the commands `context_digest.py`, `readiness.py`, `findings.py`, `finding_inbox.py`, `checklist.py`, `absorb.py`, `bug_resolution.py` over `common.py` and `phase_tasks.py`; and the gate `skill_assist_gate.py` |
| `git/` | The modules behind the `scripts/git/` wrappers rendered from the template: `status.py`, `pull.py`, `fix_line_endings.py`, `pre_review.py`, the gate `pre_review_gate.py`, `commit_and_push.py` (the pre-stage checks, themed change sets, message generation, commit and push), and `forbidden_forms.py` (the git verbs no git script may run, found by each git module's self-test in the git modules and every `datrix_scripts` module they import) |
| `claude_cli.py` | What every script that runs the Claude Code CLI shares: its name on `PATH`, and the refusal of an argument the batch shim's cmd.exe would reinterpret (`require_batch_safe`) |
| `gates/` | The modules behind gate wrappers rendered from the template, one subpackage per gate family, each module run in gate mode (its `main` is `gate_log.run_as_gate` over `gate_log.gate_child`). `gates/realization/`: one `<wrapper stem>.py` module per realization gate wrapper (`conformance_gate.py`, `standing_conformance_gate.py`, `generation_determinism_gate.py`, `pooled_cache_realization_gate.py`, …), with `generating_gates.py` (what the gates that generate share: their common options, the walk over a generated tree that prunes excluded directories and never enters a link, and one single-project generation run as a child of `datrix_scripts.dev.generate`). `gates/ratchet/`: one module per ratchet gate wrapper (`check_generated_file_ratchet.py`, `slow_test_ratchet_gate.py`, `capability_gap_ledger_gate.py`, …). `gates/parity/`: one `<wrapper stem>.py` module per parity gate wrapper (`behaviour_parity_gate.py`, `shared_home_body_gate.py`, `type_mapping_completeness.py`, …) over `gate_entry.py`, which they share: the `-Dbg`/`-SelfTest` parser, the install check, and then either the self-test with the wrapper seam checks, or the non-vacuity self-test followed by the comparison. `parity_cases_gate.py` reads the parity rows through `parity_observers.py`, and `parity_cases.py` (the `-Command` wrapper `parity-cases.ps1`) runs the authoring commands of `parity_cases_cli.py`, which cuts a replaced gate's section out of the family's `quick-reference.md` and `README.md` through `parity_doc_sections.py`. `gates/repo_hygiene/`: one `<wrapper stem>.py` module per repo-hygiene gate wrapper (`customer_domain_isolation_gate.py`, `check_docs_conformance.py`, `script_catalogue_gate.py`, `thin_entrypoint_gate.py`, `line_ending_gate.py`, `no_body_walk_gate.py`, …), with `gate_options.py` (the options and self-test parser those gates share, and the package-currency check the gates that import installed packages run first) |
| `test_result_walk.py` | Directory-only traversal yielding the `.test_results` directories of the generated tree, shared by `test\status-unit-tests.ps1` and `test\status-deploy-tests.ps1` |
| `test_runner.py`, `node_test_runner.py`, `package_suites.py` | Test execution: pytest phases, Node suites, which packages carry a suite |
| `selection_export.py` | pytest plugin a `-Tag` preflight loads: writes the node IDs and `serial` marks of the items the session kept, so the phases run exactly those |
| `runner_plugin.py`, `suite_stamp.py`, `suite_inputs.py` | The suite-input stamp: what a run touched, and the fingerprint a carried run is compared on |
| `structured_log_writer.py`, `generated_test_log_writer.py`, `deploy_test_log_writer.py`, `aggregate_test_writer.py`, `deploy_test_aggregate_writer.py` | Structured run directories (`index.json`, clusters) for package, generated-project and deploy runs |
| `codegen_hint_mapper.py` | Maps a generated file to the template and generator that probably wrote it |
| `status_tests.py` | Test status from the newest run of every package (`test\status-tests.ps1`) |
| `collect_failure_data.py`, `classify_run_delta.py`, `run_digest.py` | Failure bundle (`test\collect-failure-data.ps1`), run-to-run delta, and the short digest `test.ps1` writes to `digest.txt` for a red run |
| `cleanup_utils.py` | The yes/no confirmation (an end of input is a no), tree and file removal that clears read-only files, the removal of parents a deletion left empty and of empty folders below a folder, never at or above the base, and folder listing as `Get-ChildItem` lists (hidden entries left out, case-insensitive name order, no link entered; `tree_lines` for the `[DIR]`/`[FILE]` tree) |
| `affected_set.py` | Reverse-dependency closure of packages, from actual imports |
| `generated_example.py` | Generate one example for one registered language, as `datrix generate` would |
| `evaluate_reports.py` | The report text the evaluation scans write from their own JSON |
| `local_llm.py`, `local_llm_usage.py`, `local_llm_loopback.py` | The machines' Ollama servers (discovery, readiness, load spreading, failover), the usage log, and the loopback Ollama server every local-model check runs against |
| `local_reading.py` | Reads framework files and logs through a local model: read scope, chunking, log reduction, citation checking, the customer-term filter |
| `llm_code_fix.py` | Shared machinery for scripts that ask a local model to rewrite Python |
| `mcp_stdio.py` | The MCP protocol over stdio, shared by every Datrix MCP server |
| `mcp_exchange.py` | Talking to an MCP server in process (messages in, response lines out), for the gates that check one |
| `line_edits.py` | Line-addressed reading and editing (hash-checked line ranges, batched across files) behind the `datrix-edit` MCP server; also imported by the `route-line-edits.py` hook |
| `code_index/` | The per-machine code index: definitions, references, outlines, search, summaries, usage |
| `knowledge/` | The knowledge base behind `dev\ineedtoknow.ps1` |
| `logic_map.py` | Logic-map marker syntax, parser and the `markers.db` writer |
| `task_metadata.py`, `task_orientation.py` | Task-file and `dependencies.md` parsing; a task's `## Orientation` block |
| `customer_domain_isolation.py`, `design_task_references.py`, `ignored_source.py`, `polystring_case_roundtrip.py`, `python_lint_correctness.py` | Repo-hygiene detectors shared by their gates, the commit seam and the edit hooks |
| `behaviour_skeleton.py`, `target_literal_positions.py` | Detectors shared by the parity gates and the import-boundary scanner |
| `function_sources.py` | The one walker of module-level functions and class methods in a package tree (`collect_function_sources`), shared by the behaviour-parity and shared-home body gates and `scan\find-duplicate-bodies.ps1` |
| `body_digest.py` | A function body's comparison form (normalized and exact digests, the 8-line / 40-node floor), shared by the shared-home body gate and `scan\find-duplicate-bodies.ps1` |
| `import_sites.py` | Where a module or its names are imported across the workspace (relative imports resolved), shared by `dev\find-imports.ps1` and `codemods\split-module.ps1` |
| `plugin_discovery.py` | Loads every installed plugin group and names the one that fails; run by `datrix_scripts.dev.generate` (`dev\generate.ps1`) as a child, after the package install check, before any generation |
| `visualization/` | Application loading, serialization, diagrams and OpenAPI/AsyncAPI builders for `visualize\` |

## DatrixPaths.psm1

PowerShell module for discovering datrix workspace paths.

### Functions

```powershell
# Get workspace root (parent of datrix folder)
$root = Get-DatrixWorkspaceRoot

# Get list of repository names
$repos = Get-DatrixDirectories
# Returns: @("datrix", "datrix-cli", "datrix-common", ..., "datrix-extensions")

# Get full paths to all existing repositories
$paths = Get-DatrixDirectoryPaths

# The shared venv, its interpreter (which may not exist yet: common\venv.ps1 -Ensure creates it),
# and the directory that goes on PYTHONPATH for datrix_scripts
$venv = Get-DatrixVenvPath            # D:\datrix\.venv
$python = Get-DatrixVenvPython        # D:\datrix\.venv\Scripts\python.exe
$lib = Get-DatrixScriptsPythonPath    # D:\datrix\datrix\scripts\common\lib
```

### Workspace root

`Get-DatrixWorkspaceRoot` is the one PowerShell answer to "where is the workspace": it takes no
parameter and resolves from the module's own location, so it is the same for every script. The
Python side is `datrix_scripts.paths.WORKSPACE_DIR`.

## DatrixPythonScript.psm1

`Invoke-DatrixEntrypoint -Module <module> -Parameters $PSBoundParameters` is the body of every
wrapper rendered from the template ([above](#wrappers-rendered-from-the-template)).

`Invoke-DatrixPythonScript` (no wrapper calls it) runs a Python file (`-Script`) or module (`-Module`) in the shared
venv and returns the child's exit code (it never calls `exit`): it has the venv checked (the
`common\venv.ps1 -Ensure` check, and with `-RequirePackages` its `-EnsurePackages -SkipIfInstalled`),
prints the command with `-ShowCommand`, points the child's environment at the venv and restores the
caller's in a `finally` block. `-OutputPipeline` / `-OutputLines` hand the output lines to the caller instead of the console.
`Enter-DatrixVenvEnvironment` / `Exit-DatrixVenvEnvironment` are the environment switch both use.
The switch also has
the child write UTF-8 (`PYTHONUTF8=1`, `PYTHONIOENCODING=utf-8`) and sets the console output
encoding to UTF-8, which PowerShell uses to decode a native command's output, so non-ASCII output
(pygount's box-drawn table, check marks) is not garbled under a legacy console code page.

A script run from inside this module would run in the module's session state, where `$script:`
names that script's scope rather than the module's: the module never runs a wrapper, and the
functions a wrapper reaches keep their constants local.

**Gate mode** (`-Gate <name>`) tees the output to a claimed log under
`<workspace>\.test-output\gates\<name>\` and prints exactly one last line,
`[GATE] <name> PASSED|FAILED exit=<n> log=<path>`. That line is the seam the red-run digest hook
reads (`claude-config/.claude/hooks/digest-red-test-run.py`). A gate that runs no Python claims its
log with `New-DatrixGateLogFile` (or `Write-DatrixGateLog`) and prints the same line with
`Write-DatrixGateVerdict`.

A project MCP server's setup (`-Setup` of `dev/code-index.ps1`, `dev/local-llm.ps1`, `dev/line-edit.ps1`) is
Python: `datrix_scripts.dev.mcp_setup`. A metrics script's project selection (`-Projects` / `-All`) is
Python: `datrix_scripts.metrics.projects`.

## venv.ps1

The shared venv, `D:\datrix\.venv`. A wrapper rendered from the template; the behaviour is
`datrix_scripts.venv` (`bash common/venv.sh --help` or `python -m datrix_scripts.venv --help`
lists every option). `Invoke-DatrixEntrypoint` creates the venv with its `--ensure` when it has no
interpreter yet; a module that imports the `datrix-*` packages first runs
`datrix_scripts.venv.require_packages` (its `-Ensure -EnsurePackages -SkipIfInstalled` check), and
`test\affected-gate.ps1` runs the same check once, before any child.

| Mode | Command | What it does |
|------|---------|--------------|
| **Ensure the venv** | `.\common\venv.ps1 -Ensure` | The workspace is complete (every required repository cloned), the venv exists (created if not) and its interpreter is built for this machine's CPU |
| **Ensure the installs** | `.\common\venv.ps1 -Ensure -EnsurePackages [-SkipIfInstalled \| -Force \| -Offline]` | Reinstall every stale package, then the `[dev]` extras, then the scripts group (details below) |
| **Rebuild the venv** | `.\common\venv.ps1 -Recreate -EnsurePackages` | Build the venv afresh from a native base interpreter, then install everything |
| **Install one package** | `.\common\venv.ps1 -InstallPackage datrix-cli [-NoDev]` | Editable install, with its `[dev]` extra unless `-NoDev` |
| **Check the CLI** | `.\common\venv.ps1 -TestCommand` | `datrix --version` runs; on failure its output and exit code (or the missing executable) go to stderr and the exit code is 1 (`dev\generate.ps1` runs the same check, `datrix_scripts.venv.check_datrix_command`, after the plugin-discovery check) |
| **Base interpreter** | `.\common\venv.ps1 -BaseInterpreter` | Print the interpreter a new venv would be built from |
| **Install order** | `.\common\venv.ps1 -ListPackages` | Print the installable packages, one per line, in install order |
| **Self-test** | `.\common\venv.ps1 -SelfTest` | Planted executables, workspaces, venvs, locks and site-packages; no pip, no network |

Actions combine and run in the order `-Recreate`, `-Ensure`, `-InstallPackage`, `-EnsurePackages`,
`-TestCommand`; a query (`-BaseInterpreter`, `-ListPackages`, `-SelfTest`) runs alone. No switch is
a usage error (exit 1). `DATRIX_VENV_VERBOSE=1` prints each step; `DATRIX_OFFLINE=1` (or `-Offline`)
runs no pip.

**Python modules** call it directly: `datrix_scripts.venv.ensure_venv(WORKSPACE_LAYOUT)`,
`ensure_packages_installed(...)`, `install_order_packages(...)`, `find_base_interpreter(...)`.

### The base interpreter

The venv is built from a CPython built for the host CPU (read from the registry on Windows, never
from the process's own `PROCESSOR_ARCHITECTURE`, which an emulated process misreports), a final
release of at least datrix-common's `requires-python`, the highest version first. Candidates are
`DATRIX_PYTHON` (when set, the only one), every `python` on `PATH`, the `py` launcher's list and
uv-managed interpreters, minus Store aliases and venv interpreters. An interpreter of another
architecture runs emulated and builds native extensions (the Tree-sitter parser) for the wrong CPU:
it is refused by name, and an existing venv built from one fails `-Ensure`. The architecture is
read from the executable's header (PE, ELF or Mach-O).

`-Recreate` cannot delete the venv it runs from (a running interpreter holds its own files), so it
moves the old venv aside to `<workspace>\.venv.retired-<time>`, builds the new one, and deletes every
retired venv nothing still runs from; one still in use is named and removed by a later `-Ensure`.

### One import process per check

The installs are import-checked exactly once per check, all in one Python process:
`python -m datrix_scripts.package_imports <module> …` under the venv's interpreter, which imports
each module in order and prints `IMPORT_FAILED <module>: <ExceptionType>: <message>` per failure and
`IMPORT_CHECK <ok>/<total>` last, every line ASCII with any other character backslash-escaped so no
stream encoding can stop the verdict (exit 0 all imported, 1 any failed, 2 usage error or failed
self-test; `--self-test` runs only its self-test, which also runs first on every invocation). Each
`IMPORT_FAILED` line goes through the verbose channel. The verdict fails closed
(`datrix_scripts.venv.import_verdict`): an exit code other than the one its failures imply, or a
summary line that does not account for every module named, raises with the checker output rather
than reporting the packages importable. The module names come from the install order (on-disk
`pyproject.toml` discovery), so the checker takes no external input.

The three paths use that one result: the `-SkipIfInstalled` check and the offline check (which
names every unimportable package in its error) run it once before their loop, and the install path
runs it once before pass 1 (not under `-Force`, which reinstalls everything). Deciding whether a
package needs a reinstall starts no process. A `[dev]` marker no older than `pyproject.toml` answers
"nothing to install" without reading the TOML.

### Installs

Pass 1 reinstalls, editable and with `--no-build-isolation` (the build backends are installed
first), every package that does not import, has no install marker, or whose `pyproject.toml` or a
`src` source file (`tests`, `__pycache__`, `.generated` and `.pytest_cache` excluded) is newer than
the marker. Pass 2 installs each package's `[dev]` extra -- only after every package is installed,
since a dev spec may name a sibling, which would otherwise resolve against PyPI on a rebuild from
scratch. Pass 3 installs the scripts tree's own third-party tools, the `scripts` dependency group
of `datrix/pyproject.toml`. Every pip call runs `<venv python> -m pip` by path, from the package's
own directory (a relative `file:` spec resolves from the working directory), with its temp and
cache directories under `<workspace>\.tmp`. Install markers where editable installs are missing
(an interrupted pip run) are removed first, so everything reinstalls; `~`-prefixed leftovers of
interrupted pip runs are deleted from site-packages.

### Concurrent operation safety

Every install holds one workspace-wide lock, `<workspace>\.venv-package.lock` (a JSON file with
the pid, timestamp and script, created atomically), waiting up to 120 seconds. A lock older than 300
seconds, one whose process is gone, or one that cannot be read is removed. The lock is re-entrant
within a process, released only by the process that wrote it, and released at exit if a run ends
holding it.

## Usage in Scripts

A wrapper is its help, `[CmdletBinding()]` and `param()` block, then the template's tail unchanged:

```powershell
[CmdletBinding()]
param(
 [string[]]$Projects, [switch]$All, [switch]$Dbg, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, ...
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.<category>.<name>" -Parameters $PSBoundParameters
exit $LASTEXITCODE
```

Everything else, project discovery (`-Projects` / `-All`) included, is the module's: through
`datrix_scripts.metrics.projects` or `datrix_scripts.framework_repos`, never in the wrapper.

## Cleanup scripts

The cleanup scripts (`workspace\cleanup-temps.ps1`, `workspace\empty-folders.ps1`, `test\cleanup.ps1`,
`tasks\cleanup.ps1`, `metrics\cleanup-ruff.ps1`) share `datrix_scripts.cleanup_utils`: the typed
`yes` / `no` confirmation (an end of input answers no), tree and file removal, pruning the folders a
deletion left empty up to a boundary, a listing that never enters a link, and `format_cleanup_size`
byte sizes. Their self-tests answer the confirmation with `scripted_answers` / `refuse_answer`.

## DatrixRunLog.psm1

Names a run's log file, and claims it so no other run can be handed the same one.

```powershell
$base = Get-DatrixRunLogBaseName -Prefix "generate-results" -Segment @($Language, $ConfigProfile)
$logFile = New-DatrixRunLogFile -Directory $resultsDir -BaseName $base
```

- `ConvertTo-DatrixRunLogSegment` — reduce one label to name-safe characters (a label from a command line can never traverse out of the results directory)
- `Get-DatrixRunLogBaseName` — `<prefix>-<timestamp>[-<label>...]`, timestamp leading so name-sorting stays chronological; pass `-Timestamp` to compose deterministically
- `New-DatrixRunLogFile` — creates and returns a log file this run owns alone

**The labels are not what makes the name unique.** Two runs agreeing on every label
(two profiles of one project started in the same second, or two runs of one profile)
compute one name; `New-DatrixRunLogFile` claims it with `FileMode.CreateNew`, an atomic
create-or-fail, and falls through to `<base>-2`, `<base>-3`, … when a name is taken.
Never relax that to `Create`/`OpenOrCreate` — both succeed on an existing file, which is
how two runs end up truncating and interleaving one log.

File-level twin of `TeeLogger._claim_run_dir` (`scripts/common/lib/datrix_scripts/logging_utils.py`),
which does the same for test run *directories*. Held by
`scripts/test/run-log-exclusivity-gate.ps1`.
