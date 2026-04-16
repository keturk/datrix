# Library

Python implementations called by PowerShell wrapper scripts.

## Structure

```
library/
├── dev/ # Development tools
├── metrics/ # Code metrics: Radon, Vulture, Ruff, duplicate-code, Bandit
├── shared/ # Shared utilities
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

## shared/

Shared utilities used across multiple scripts.

| File | Description |
|------|-------------|
| `test_runner.py` | Test execution framework |
| `test_projects.py` | Project discovery from test-projects.json |
| `logging_utils.py` | Logging configuration |
| `venv.py` | Virtual environment utilities (Python side) |

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

## Adding New Scripts

1. Create Python implementation in appropriate `library/` subfolder
2. Create PowerShell wrapper in corresponding category folder
3. Wrapper should:
 - Import `common/DatrixScriptCommon.psm1` (or `DatrixPaths.psm1` only if no shared discovery needed), dot-source `common/venv.ps1`
 - Call `Ensure-DatrixVenv` and `Ensure-DatrixPackagesInstalled`
 - Execute Python script with proper argument passing
 - Handle cleanup on exit
