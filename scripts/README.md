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

1. **PowerShell wrappers** (`.ps1`) in each folder handle virtual environment activation, dependency
   installation, argument parsing and validation, and logging and cleanup.
2. **Python implementations** (`.py`) sit beside the wrapper that runs them, in that folder's `lib/`
   (`gates/<family>/lib/` for gates). A module imported from more than one folder, by a hook, or by
   a package test lives in `common/lib/datrix_scripts/` and is imported as `datrix_scripts.<name>`;
   a wrapper runs one of those with `python -m datrix_scripts.<name>`.

Every wrapper runs its Python through `Invoke-DatrixPythonScript` (`common/DatrixPythonScript.psm1`),
which activates the shared venv with `common/lib` on `PYTHONPATH`, so every wrapper's Python can
import the shared package. The placement rule, how hooks and MCP servers reach the package, and how to add a
script are in [common/README.md](common/README.md#where-python-lives).
`test\shared-library-gate.ps1 -Only check_scripts_tree` holds the layout.

## Project discovery (PowerShell)

Different scripts use different ways to decide which packages to include:

| Use case | Helper (see `common/DatrixScriptCommon.psm1`) | Meaning |
|----------|-----------------------------------------------|---------|
| Metrics `-All` (Ruff, complexity, …) | `Get-DatrixPackageNamesGlob` | Every directory under the workspace named `datrix-*` |
| `test.ps1 -All` | `Get-DatrixTestablePackageNames` | `datrix-*` directories carrying a test suite: a `tests/` folder (pytest) or a `package.json` with a `test` script (Node) |
| `duplicate.ps1 -Mono` | `Get-DatrixMonoProjectNames` | Ordered canonical package names (`Get-DatrixDirectories`) where the path exists |
| `dependency.ps1` help text | `Get-DatrixPackageNamesGlobWithPyProject` | `datrix-*` directories that contain `pyproject.toml` |

`Get-DatrixTestablePackageNames` is the PowerShell half of one fact; the Python half is
`common/lib/datrix_scripts/package_suites.py`, which `status-tests.ps1`, `test_project.py` and
`gate-verdict.ps1` use. Neither can call the other — the PowerShell answer is needed before
the venv is activated — so `test/test-tooling-parsing-gate.ps1` compares the two sets on every
run rather than leaving them to drift.

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

Every script's forms and parameters live in its folder's quick-reference: start at [quick-reference.md](quick-reference.md), which links each category's reference and shows the forms an agent may run (targeted tests, one project's generation, one named scan rule) apart from Jon's sweeps. The anti-pattern scanners' rule catalogs are [config/semgrep-rules/README.md](config/semgrep-rules/README.md) and [config/ast-grep-rules/README.md](config/ast-grep-rules/README.md); the codemods are described in [codemods/README.md](codemods/README.md).

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
- [test/quick-reference.md](test/quick-reference.md) - Test runner, status, failure analysis, test-tooling gates
- [gates/README.md](gates/README.md) - Repo-level gates by family
- [dev/quick-reference.md](dev/quick-reference.md) - Generation, code index, local models, ineedtoknow, docs checks
- [generation/quick-reference.md](generation/quick-reference.md) - Parser, snapshots, triage, evaluation
- [scan/quick-reference.md](scan/quick-reference.md) - Anti-pattern scanners, import boundaries, compile checks
- [workspace/quick-reference.md](workspace/quick-reference.md) - Listing, counting, cleanup
- [git/quick-reference.md](git/quick-reference.md) - Git operations
- [metrics/quick-reference.md](metrics/quick-reference.md) - Code quality and metrics
- [review/quick-reference.md](review/quick-reference.md) - Task-file review
- [visualize/quick-reference.md](visualize/quick-reference.md) - Visualization and documentation
- [tasks/quick-reference.md](tasks/quick-reference.md) - Task management
- [skill/quick-reference.md](skill/quick-reference.md) - Headless skill chains and skill assists
- Individual folder READMEs for detailed documentation
