# Library

Python implementations called by PowerShell wrapper scripts.

## Structure

```
library/
├── code_index/ # Per-machine code index: definitions, references, search, logic-map markers
├── dev/ # Development tools
├── metrics/ # Code metrics: Radon, Vulture, Ruff, duplicate-code, Bandit
├── review/ # Task-file review tooling (Tier 1/2 reviewer + apply-reviews prep)
├── shared/ # Shared utilities
├── skill/ # Skill assists: the mechanical phases of agent skills (wrapper: skill/skill-assist.ps1)
├── tasks/ # Task-file management and phase analysis
└── test/ # Test utilities
```

## dev/

Development tool implementations.

| File | Wrapper | Description |
|------|---------|-------------|
| `generate.py` | `dev/generate.ps1` | Code generation from .dtrx files |
| `rebuild_parser.py` | `dev/rebuild-parser.ps1` | Tree-sitter parser rebuilding |
| `ruff_checker.py` | `dev/ruff-checker.ps1` | Jinja2 template linting |
| `syntax_checker.py` | `dev/syntax-checker.ps1` | .dtrx syntax validation |
| `conformance_gate.py` | `dev/conformance-gate.ps1` | Declarative design-acceptance assertion runner (spec JSON, non-vacuity control, self-testing) |
| `gendsl_census.py` | `dev/gendsl-census.ps1` | Per-domain genDSL census + double-emit offender detection |
| `evaluate_generated_scan.py` | `dev/evaluate-generated-scan.ps1` | Project-level generated-output scan for `/evaluate-generated` (inventory, manifests, infra checks, prompts) |
| `evaluate_service_scan.py` | `dev/evaluate-service-scan.ps1` | Service-level scan for `/evaluate-generated-service` (DSL inventory, manifest set-diff, artifact existence, dead-code candidates) |
| `code_index_cli.py` | `dev/code-index.ps1` | Code index queries (definitions, references, outline, search, logic-map markers, status, summaries) |
| `code_index_mcp.py` | (registered with Claude Code by `code-index.ps1 -Setup`) | The code index as a stdio MCP server; standard library only |
| `local_llm_mcp.py` | (registered with Claude Code by `local-llm.ps1 -Setup`) | The local model servers as a stdio MCP server: `ask_files`, `digest_log`, `local_models` |
| `local_llm_cli.py` | `dev/local-llm.ps1` | Local model status and usage report |
| `logic_map.py` | (library) | Logic-map marker syntax, parser, and the `markers.db` writer the code index calls |
| `code_scan.py` | `dev/code-scan.ps1` | On-demand digest of dead code (Vulture, confirmed against the code index and string uses), complexity, duplicates and docs drift for changed packages |

## git/

| File | Wrapper | Description |
|------|---------|-------------|
| `commit-and-push.py` | `git/commit-and-push.ps1` | Themed commits with local-model (or Claude CLI) messages, then push |
| `pre_review.py` | `git/pre-review.ps1` | Definite syntax-tree checks on the lines pending changes add to Python files; opt-in advisory local-model review |

## code_index/

The code index, one per development machine, kept at `<workspace>/.code-index/` and refreshed incrementally before every query. See `dev/quick-reference.md` § `dev\code-index.ps1`.

| File | Description |
|------|-------------|
| `sources.py` | Configuration (`config/code-index.json`), the git-visible file set, module names |
| `extract.py` | One file's definitions, imports, references and markers, from its syntax tree |
| `store.py` | The `index.db` schema and per-file writes; `summaries.db`, which survives rebuilds |
| `refresh.py` | Incremental refresh (size/mtime, then hash) and the `markers.db` rewrite |
| `queries.py` | Definitions, import-resolved references, outline, full-text search, canonical markers, status |
| `summaries.py` | Local-model module summaries, cached by content hash (run only when asked) |
| `session.py` | Open the workspace's index |

## shared/

Shared utilities used across multiple scripts.

| File | Description |
|------|-------------|
| `test_runner.py` | Test execution framework |
| `test_projects.py` | Project discovery from test-projects.json |
| `logging_utils.py` | Logging and tee-style output (console + file) |
| `registered_targets.py` | Canonical enumeration of registered `datrix.languages`/`datrix.platforms` targets (entry-point name discovery) plus on-disk `src/` directory resolution for those targets (`discover_target_package_src_dirs`, `discover_all_other_package_src_dirs`) -- the one place every script sources "which targets exist" and "where do they live on disk" |
| `structured_log_writer.py` | Post-processes JUnit XML into structured test result directories (codegen package tests via `test.ps1`) |
| `generated_test_log_writer.py` | Post-processes JUnit XML and Jest JSON into structured test result directories for generated projects (multi-service, cross-project aggregation, codegen hints). Called from `run_complete.py`. Shares clustering/normalization utilities with `structured_log_writer.py`. Its `index.json` lists every executed test in `tests` (`{service, test, outcome}`), which `test/generated_suite_parity.py` reads to compare the generated suites across languages. |
| `venv.py` | Virtual environment utilities (Python side) |
| `framework_repos.py` | The framework git repositories at the workspace root (`datrix` and every `datrix-*`), discovered, never listed |
| `local_llm.py` | Local model servers on the network: discovery, readiness, load spreading over every ready server, failover; every request recorded through `local_llm_usage.py` |
| `local_llm_usage.py` | The per-machine local-model usage log (`<workspace>/.local-llm/usage.jsonl`, sizes only, never text) and its report |
| `local_reading.py` | Reads framework files and logs through a local model so an agent gets a cited answer instead of the text: read scope, line numbering, chunking, log reduction, citation checking |
| `mcp_stdio.py` | The MCP protocol over stdio shared by every Datrix MCP server; standard library only |

## metrics/

Code metrics and analysis: Radon (complexity, raw, Halstead, MI), Vulture, Ruff, Pylint duplicate-code, and Bandit security scanning.

| File | Description |
|------|-------------|
| `complexity.py` | Radon metrics (check, cc, raw, halstead, mi) |
| `vulture.py` | Vulture dead-code detection |
| `ruff.py` | Ruff lint/format |
| `dependency.py` | Datrix package dependency graph (tree, list, json) from pyproject.toml |
| `duplicate.py` | Pylint duplicate-code detection (R0801) |
| `bandit.py` | Bandit security scanner |
| `utils.py` | Shared utility functions (venv helpers) |

## test/

Test execution utilities.

| File | Wrapper | Description |
|------|---------|-------------|
| `test_project.py` | `test/test.ps1` | Main test runner for projects |
| `run_complete.py` | `test/run-complete.ps1` | Complete test suite runner |
| `status_tests.py` | `test/status-tests.ps1` | Test status reporting |
| `status_unit_tests.py` | `test/status-unit-tests.ps1` | Running test status |
| `status_deploy_tests.py` | `test/status-deploy-tests.ps1` | Deployment test status |
| `collect_failure_data.py` | `test/collect-failure-data.ps1` | Failure bundle (`failure-data.json`) from a structured run dir: clusters grouped into families with one traceback tail each, capped messages, advisory local-model hints; supports package, generated-unit, and deploy index schemas |
| `extract_warnings.py` | `test/extract-warnings.ps1` | Deduplicated pytest warnings (`warnings.json`) parsed from a run's `full.log` |
| `classify_run_delta.py` | `test/classify-run-delta.ps1` | SUCCESS/PARTIAL/NO_CHANGE/REGRESSION verdict (`run-delta.json`) between two runs of one package |
| `run_digest.py` | `test/test.ps1` (after the summary, per failed package) | Short failure digest (`digest.txt`): the failure families with location and re-run command, the change since the last run with the same selection, and resident local-model hints plus one cross-group reading; `--self-test` checks it against a temp workspace and a loopback model server |
| `gate_verdict.py` | `test/gate-verdict.ps1` | GREEN/RED aggregate verdict over packages' newest runs (fail-loud on missing/in-progress results) |

## tasks/

Task-file management and phase analysis.

| File | Wrapper | Description |
|------|---------|-------------|
| `complete.py` | `tasks/complete.ps1` | Mark a task file COMPLETED (validation-hooked) |
| `task_metadata.py` | (shared module) | Task-file + dependencies.md parsing (JSON and legacy formats) used by the three scripts below |
| `phase_status.py` | `tasks/phase-status.ps1` | Full per-task metadata snapshot of a phase across all repos |
| `plan_waves.py` | `tasks/plan-waves.ps1` | Kahn waves, cycle/conflict/blocker detection, QG-last ordering |
| `validate_dependencies.py` | `tasks/validate-dependencies.ps1` | dependencies.md + numbering validation; `-NextTaskNumber` mode |
| `task_orientation.py` | (shared module) | A task's `## Orientation` block: parse and validate (rejects "where is X defined / who calls X" questions), resolve facts from the code index and explanations through a local model |
| `task_citations.py` | (shared module) | Checks every `path:line` citation in a task's prose against the tree (missing file, line past the end, name beside the citation no longer near its lines); never guesses between same-named files |
| `retrofit_orientation.py` | `tasks/retrofit-orientation.ps1` | Gives tasks written before the `## Orientation` block existed one, deterministically: whole-file review items the task does not edit become exact `outline:` entries (their lines leave the review list), unique cited functions become `symbol:` entries; dry run unless `-Apply`, originals copied aside, idempotent |
| `validate_task.py` | `tasks/validate-task.ps1` | Validates task files against the tree as it is now: orientation resolves, citations hold; run by writers, by orchestrators before each wave |

## review/

| File | Wrapper | Description |
|------|---------|-------------|
| `review.py` | (direct: `python review.py`) | Tier 1 + Tier 2 task file reviewer |
| `apply_reviews_prep.py` | `review/apply-reviews-prep.ps1` | Discover/validate/dedupe review findings into the `/apply-reviews` worklist |

## Adding New Scripts

1. Create Python implementation in appropriate `library/` subfolder
2. Create PowerShell wrapper in corresponding category folder
3. Wrapper should:
 - Import `common/DatrixScriptCommon.psm1` (or `DatrixPaths.psm1` only if no shared discovery needed), dot-source `common/venv.ps1`
 - Call `Ensure-DatrixVenv` and `Ensure-DatrixPackagesInstalled`
 - Execute Python script with proper argument passing
 - Handle cleanup on exit
