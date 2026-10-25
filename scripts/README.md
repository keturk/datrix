# Datrix Scripts

PowerShell wrapper scripts and their Python implementations for development, testing, and maintenance of the Datrix ecosystem.

## Folder Structure

```
scripts/
├── common/       # Shared PowerShell modules, the wrapper template, venv.ps1, and lib/datrix_scripts (the shared Python package)
├── config/       # Configuration: test projects, baselines, exemptions, scanner rules
│   ├── semgrep-rules/      # Individual YAML rule files for the Semgrep anti-pattern scanner
│   ├── ast-grep-rules/     # Individual YAML rule files for the ast-grep structural scanner
│   └── conformance-specs/  # Committed specs for the standing conformance gate
├── dev/          # Generation, import/parse-tree lookups, the code index, local model servers, ineedtoknow, docs checks, code-health digests
├── generation/   # Parser rebuild, example snapshots, seed datasets, generation status/triage, generated-tree comparison, evaluation scans
├── scan/         # Anti-pattern scanners, import boundaries, compile/syntax checks, generated-output audits, duplicate-body/abstract-method reports
├── workspace/    # Project listing, structure files, counts, cache and empty-folder cleanup
├── codemods/     # Bowler/libCST codemods and the module splitter for refactoring Datrix Python code
├── test/         # The test runner, status and failure analysis, test-tooling gates
├── gates/        # Repo-level validation gates
│   ├── parity/        # Every target realizes the same thing the same way
│   ├── realization/   # A declared capability is actually realized
│   ├── ratchet/       # Counts that only move one way
│   └── repo-hygiene/  # What may be committed; docs, examples, hard-zero code shapes
├── git/          # Git operations across all repositories (status, pull, line endings, review, commit)
├── metrics/      # Code metrics: Radon, Vulture, Ruff, dependency, duplicate-code, Bandit, coverage, agent spend
├── review/       # Task-file review (Tier 1 per task, Tier 2 per phase, both on local models)
├── skill/        # Headless skill chains and skill assists
├── tasks/        # Task-file management and phase analysis
└── visualize/    # Diagrams, OpenAPI/AsyncAPI documents, schema snapshots
```

## Architecture

The scripts follow a **wrapper pattern**:

1. **PowerShell wrappers** (`.ps1`) in each folder are the template `common/templates/entrypoint.ps1`
   rendered with the script's own help, `param()` block and module, each with a POSIX twin (`.sh`)
   rendered from `common/templates/entrypoint.sh`. `gates\repo-hygiene\thin-entrypoint-gate.ps1`
   holds every `.ps1` to that form.
2. **Python implementations** (`.py`) are modules of the shared package in `common/lib/datrix_scripts/`
   (`datrix_scripts.<category>.<script>`, gates under `datrix_scripts.gates.<family>`), run with
   `python -m`. The one `lib/` folder beside a wrapper is `codemods/lib/`, recipes loaded by path.

Every wrapper runs its module through `Invoke-DatrixEntrypoint` (`common/DatrixPythonScript.psm1`),
which activates the shared venv with `common/lib` on `PYTHONPATH`, so every wrapper's Python can
import the shared package. The placement rule, how hooks and MCP servers reach the package, and how to add a
script are in [common/README.md](common/README.md#where-python-lives).
`test\shared-library-gate.ps1 -Only check_scripts_tree` holds the layout.

## Project discovery

Different scripts use different ways to decide which packages to include:

| Use case | Helper (Python) | Meaning |
|----------|-----------------|---------|
| A metrics script (`-All`) | `datrix_scripts.metrics.projects.select_projects` | Every directory under the workspace named `datrix-*`, sorted |
| `duplicate.ps1 -Mono` | `framework_repos.workspace_package_dirs(..., include_showcase=True)` | The `datrix` showcase repo, then every `datrix-*` directory, sorted |
| `dependency.ps1` (`-All` and its usage text) | `select_projects(..., any_of={PackageMarker.PYPROJECT})` | `datrix-*` directories that contain `pyproject.toml` |

Which packages carry a test suite (`test.ps1 -All`, `status-tests.ps1`, `test_project.py`,
`gate-verdict.ps1`) is answered in Python alone: `testable_package_names` in
`common/lib/datrix_scripts/package_suites.py` — `datrix-*` directories with a `tests/` folder
(pytest) or a `package.json` with a `test` script (Node).

## Bash Shell Invocation

All examples in this documentation use **PowerShell-native** syntax (e.g., `.\test\test.ps1`). If you are running from a **bash** shell (e.g., AI agents, Git Bash, WSL), you must:

1. Prefix with `powershell -File`
2. Use **forward slashes** in paths (never `\\` or unquoted `\`)
3. Quote the script path

```bash
# PowerShell:  .\test\test.ps1 datrix-common -Specific "tests/unit/test_foo.py"
# Bash equivalent:
powershell -File "d:/datrix/datrix/scripts/test/test.ps1" datrix-common -Specific "tests/unit/test_foo.py"
```

See [quick-reference.md](quick-reference.md) for the full conversion table and links to category-specific references.

## Quick Start

Every script's forms and parameters live in its folder's quick-reference: start at [quick-reference.md](quick-reference.md), which links each category's reference and shows the forms an agent may run (targeted tests, one project's generation, one named scan rule). Each folder's README explains what its scripts do. The anti-pattern scanners' rule catalogs are [config/semgrep-rules/README.md](config/semgrep-rules/README.md) and [config/ast-grep-rules/README.md](config/ast-grep-rules/README.md); the codemods are described in [codemods/README.md](codemods/README.md).

## Workspace root and wrappers

`Get-DatrixWorkspaceRoot` (`common/DatrixPaths.psm1`) is the monorepo root in PowerShell,
`datrix_scripts.paths.WORKSPACE_DIR` in Python. Every wrapper runs its Python through
`common/DatrixPythonScript.psm1`: a wrapper rendered from `common/templates/entrypoint.ps1` (with a `.sh`
POSIX twin) through `Invoke-DatrixEntrypoint`, passing each parameter as `--kebab-name` to its
`datrix_scripts` module, any other through `Invoke-DatrixPythonScript`
([common/README.md](common/README.md)); the shared venv is `common/venv.ps1`.

**Working directory.** Commands assume you are in `datrix/` (the showcase root). From the workspace root
(the parent of `datrix`), prefix script paths with `.\datrix\` (e.g. `.\datrix\scripts\test\test.ps1`).
This applies to source arguments too: an `examples/...` argument is resolved against the current working
directory, so from the workspace root it must be given as `datrix/examples/...`. The documented
`examples/...` form fails from there with `Source file or directory not found`:

```powershell
# from workspace root D:\datrix
powershell -File "d:/datrix/datrix/scripts/dev/generate.ps1" "datrix/examples/03-domains/ecommerce/system.dtrx" -L python
```

**Project names** are discovered from disk — any `datrix-*` directory in the workspace is a valid
`-Projects` value (`Get-DatrixDirectories`). The venv scripts narrow to packages carrying a
`pyproject.toml`; the test scripts narrow to packages carrying a *suite*, which is a `tests/` folder
(pytest) or a `package.json` declaring a `test` script (Node). A new `datrix-codegen-<lang>` package
becomes a valid project name as soon as its directory exists, with no edit here. The showcase repo `datrix`
(docs, examples, scripts) and `datrix-vscode` (a VS Code client in TypeScript whose suite runs under Node,
not pytest) are valid names too.

**Common options.** Each script declares its own parameters, and its folder's quick reference lists exactly
those (held by `gates\repo-hygiene\script-catalogue-gate.ps1`). Many take `-Dbg` (debug logging) and folder
paths as input (`.\datrix-common\` instead of `datrix-common`). An `-All` form, where a script has one,
sweeps every package: test, scan and generation sweeps are refused to agents by the hooks and belong to
Jon's terminal (below).

## Generation categories and test sets

For `generate.ps1` and `run-complete.ps1` batch mode:

| Flag | Path / Test Set | Content |
|------|------|---------|
| `-TestSet foundation` | `examples/01-foundation/` | Foundation examples |
| `-Domains` | `examples/03-domains/` (`domains`) | Domain examples |
| `-TestSet non-foundation` | `all` minus `foundation` | Everything except foundation examples |
| `-TestSet <name>` | Any test set from test-projects.json | Custom test set |

| Test Set | Content |
|----------|---------|
| `foundation` | Foundation examples (`examples/01-foundation`) |
| `non-foundation` | Everything except foundation examples |
| `features-core` | Core feature examples (entities, enums, REST API, etc.) |
| `features` | All feature examples (`examples/02-features`) |
| `typescript-validation` | Representative subset for TypeScript validation (01-basic-entity, 03-basic-api, 05-relationships, 09-events, 15-cache, 20-cqrs, 21-background-jobs, blog-cms) |
| `domains` | All domain examples (`examples/03-domains`) |
| `all` | Every example (default for `-All`) |

## What each category covers

- **Testing** ([test/](test/README.md)): `test.ps1` (`-ListTags` also reports tags missing from the vocabulary table), `cases.ps1` (declarative test cases: observe, new, migrate, accept, check), `model-contracts.ps1` (schema-derived model contracts: facts, inventory, migrate, accept), `tables.ps1` (table contracts, one item per table row: rows, inventory, migrate, accept), the run, status and failure-analysis scripts, and the test-tooling gates (`shared-library-gate.ps1` also holds the scripts-tree layout).
- **Gates** ([gates/README.md](gates/README.md)): [parity](gates/parity/README.md) (parity-cases — every probe-read parity fact is a row of `gates/parity/cases/*.parity.yaml`, authored with `parity-cases.ps1` — type-mapping-completeness, supported-domain, behaviour, shared-home-body, observability-axis, manifest-import, third-party-dependency, framework-header, response-body-transform-census, problem-type), [realization](gates/realization/README.md) (conformance-gate, standing-conformance, typescript-whole-system, generation-determinism, ingress-migration, shared-builder-reachability, zero-environment-runtime, model-realization, pooled/shared-cache, shared-rdbms, documentation-realization, dgen-corpus-resolution), [ratchet](gates/ratchet/README.md) (check-generated-file-ratchet, dependency-declaration, migration-upgrade-op-family, capability-gap-ledger, slow-test), [repo-hygiene](gates/repo-hygiene/README.md) (customer-domain-isolation, retired-dsl-names, design-task-reference, line-ending, ignored-source, polystring-case-roundtrip, python-lint-correctness, import-name-existence, check-docs-conformance, instruction-surface, cross-package-fixture-reads, enum-value-literals, handler-name-dedup, observability-native-only, emitted-escape-integrity, app-probe-path-literal, example-registry/snapshot/secret-seed/config-load, source-comment-reference, no-body-walk, script-catalogue, thin-entrypoint, no-import-registration, stateless-generator, seal-integrity).
- **Development** ([dev/](dev/README.md)): `generate.ps1` (checks the CLI and that every plugin loads before generating), the code index, local model servers, `ineedtoknow.ps1`, docs checks and their gates.
- **Git** ([git/](git/README.md)): `pull.ps1` labels each blocked path OVERLAPS/DISJOINT/…; `resolve-pull.ps1` pulls over local work for `/resolve-conflicts`; `commit-and-push.ps1` refuses to commit customer domain language (`gates/repo-hygiene/customer-domain-isolation-gate.ps1`), a tree where a `.gitignore` rule shadows a source file (`ignored-source-gate.ps1`), a `to_*_case(str(name))` round trip (`polystring-case-roundtrip-gate.ps1`), a pyflakes or top-level blank-line (E302/E305) finding in a pending `.py` file (`python-lint-correctness-gate.ps1`), or a design-doc, task-file or item-label reference (`design-task-reference-gate.ps1`).
- **Metrics** ([metrics/](metrics/README.md)): `complexity.ps1` (`-Files` for named files), `dependency.ps1` (`-Mode third-party`), `agent-spend.ps1`, and the Ruff, Bandit, dead-code, coverage, duplicate and size reports.
- **Generation, scan, workspace, visualize, tasks, review, skill**: see each folder's README.

## File locations

| What | Where |
|------|-------|
| Virtual environment | `D:\datrix\.venv` |
| Generation logs | `.generated/.results/generate-results-<timestamp>-<language>[-<profile>][-N].log` — the `-N` suffix appears when another run already claimed that name |
| Test results | `<project>/.test_results/test-results-YYYYMMDD-HHMMSS/` for package tests; generated projects also use `unit-tests-YYYYMMDD-HHMMSS/` and `deploy-test-YYYYMMDD-HHMMSS/` |
| Ruff check logs | `D:\datrix\.test-output\ruff\<project>\ruff-YYYYMMDD-HHMMSS.log` — outside every package repo |
| Test config | `scripts/config/test-projects.json` |
| Semgrep rules | `scripts/config/semgrep-rules/` |
| ast-grep rules | `scripts/config/ast-grep-rules/` |
| Metrics scripts | `scripts/metrics/` |
| Anti-pattern scanners | `scripts/scan/libcst.ps1`, `scripts/scan/semgrep.ps1`, `scripts/scan/ast-grep.ps1` |
| `.dcfg` lint/format | `scripts/scan/config-linter.ps1` |
| Code index (per machine) | `d:\datrix\.code-index\` — built and refreshed by `scripts/dev/code-index.ps1` (set up each machine once with `-Setup`) |
| Local model servers (per machine) | `scripts/dev/local-llm.ps1` — `-Setup` puts the agents' local-model MCP tools in `d:\datrix\.mcp.json` and approves them, once per machine; `-Status`/`-Usage` show what answers and what used it (`d:\datrix\.local-llm\usage.jsonl`) |
| Knowledge base (per machine) | `scripts/dev/ineedtoknow.ps1 "<question>"` — brief answer from the docs and earlier learned answers, or a local-model read of the closest docs that is kept only when its citations hold; database `d:\datrix\.knowledge\knowledge.db`, committed text copy of learned answers `datrix\docs\knowledge\learned\` |
| Logic map database | `d:\datrix\.logic-map\markers.db` — rewritten by the code index whenever markers change |
| Logic map scripts | `scripts/dev/code-index.ps1 -Canonical`, `scripts/dev/logic-map-report.ps1` |
| Python implementations | `scripts/common/lib/datrix_scripts/<category>/` (gates in `datrix_scripts/gates/<family>/`), each run by its rendered wrapper with `python -m`; `scripts/codemods/lib/` holds the Bowler recipes loaded by path |
| Cleanup utilities | `scripts/common/lib/datrix_scripts/cleanup_utils.py` (the yes/no confirmation, tree and file removal, emptied-parent pruning, link-safe listing) |
| Run-log naming/claiming | `scripts/common/DatrixRunLog.psm1` |
| Skill scripts | `scripts/skill/` — headless skill chains (each step a `claude -p` run on its skill's own model) and the skill assists; Python in `scripts/common/lib/datrix_scripts/skill/` |

## Jon's terminal (refused to agents by the hooks)

Whole-suite, whole-corpus and whole-package sweeps: an agent's hooks refuse them
(`guard-full-suite-runs.py`, `validate-script-invocation.py`, `guard-untargeted-scans.py`).

```powershell
.\test\test.ps1 -All -Coverage
.\dev\generate.ps1 -TestSet foundation -L python
.\test\run-complete.ps1 -All -L python
.\metrics\ruff.ps1 -All
.\metrics\bandit.ps1 -All
.\metrics\duplicate.ps1 -All
.\scan\libcst.ps1 -All
.\scan\semgrep.ps1 -All
.\scan\ast-grep.ps1 -All
```

## Other workflows

```powershell
# Full cleanup
.\workspace\cleanup-temps.ps1 -Force
.\test\cleanup.ps1 -Force
.\metrics\cleanup-ruff.ps1 -Force
.\generation\delete-generated.ps1

# Documentation checks
.\dev\check-docs.ps1
.\dev\generate-doc-fragments.ps1 -Check

# Check generation status
.\generation\status-generation.ps1
.\test\status-tests.ps1
.\test\status-deploy-tests.ps1
```

## Virtual Environment

All scripts use a shared virtual environment at `D:\datrix\.venv`. `common/venv.ps1` (its POSIX twin
`common/venv.sh`; the behaviour is `datrix_scripts.venv`) handles:

- Venv creation from a CPython built for the host CPU, when missing or on `-Recreate`
- Package installation with locking (prevents concurrent pip operations)
- Editable install management for all datrix-* packages, their `[dev]` extras and the scripts group

Every wrapper runs its Python with the venv's interpreter and `PYTHONPATH` pointing at the shared
scripts package (`common/DatrixPythonScript.psm1`); a wrapper rendered from
`common/templates/entrypoint.ps1` creates the venv first when it does not exist yet.

## Prerequisites

- PowerShell 5.1+ or PowerShell Core 7+
- Python 3.11+
- Git

## See Also

- [quick-reference.md](quick-reference.md) - AI agent quick reference (index with links to category files)

Each folder keeps two files: a `quick-reference.md` (how to run each script: forms, parameters, exit
codes) and a `README.md` (what each script does, how it decides, what it records or proves).

| Folder | Run it | Understand it |
|--------|--------|---------------|
| `test/` | [quick-reference](test/quick-reference.md) | [README](test/README.md) — test runner, status, failure analysis, test-tooling gates, `index.json` schemas |
| `gates/` | per family below | [README](gates/README.md) — repo-level gates by family |
| `gates/parity/` | [quick-reference](gates/parity/quick-reference.md) | [README](gates/parity/README.md) |
| `gates/realization/` | [quick-reference](gates/realization/quick-reference.md) | [README](gates/realization/README.md) |
| `gates/ratchet/` | [quick-reference](gates/ratchet/quick-reference.md) | [README](gates/ratchet/README.md) |
| `gates/repo-hygiene/` | [quick-reference](gates/repo-hygiene/quick-reference.md) | [README](gates/repo-hygiene/README.md) |
| `dev/` | [quick-reference](dev/quick-reference.md) | [README](dev/README.md) — generation, code index, local models, ineedtoknow, docs checks |
| `generation/` | [quick-reference](generation/quick-reference.md) | [README](generation/README.md) — parser, snapshots, triage, evaluation |
| `scan/` | [quick-reference](scan/quick-reference.md) | [README](scan/README.md) — anti-pattern scanners, import boundaries, compile checks |
| `workspace/` | [quick-reference](workspace/quick-reference.md) | [README](workspace/README.md) — listing, counting, cleanup |
| `git/` | [quick-reference](git/quick-reference.md) | [README](git/README.md) — git operations |
| `metrics/` | [quick-reference](metrics/quick-reference.md) | [README](metrics/README.md) — code quality and metrics |
| `review/` | [quick-reference](review/quick-reference.md) | [README](review/README.md) — task-file review |
| `visualize/` | [quick-reference](visualize/quick-reference.md) | [README](visualize/README.md) — visualization and documentation |
| `tasks/` | [quick-reference](tasks/quick-reference.md) | [README](tasks/README.md) — task management |
| `skill/` | [quick-reference](skill/quick-reference.md) | [README](skill/README.md) — headless skill chains and skill assists |
| `codemods/` | [README](codemods/README.md) | |
