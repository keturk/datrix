# Test Scripts

Test execution and status reporting scripts.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/test/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `test.ps1` | Main test runner for projects |
| `run-complete.ps1` | Run complete test suite |
| `status-tests.ps1` | Show test status summary |
| `status-unit-tests.ps1` | Show running test status |
| `status-deploy-tests.ps1` | Show deployment test status |
| `compare-tests.ps1` | Compare timestamped unit/deploy test runs for one project |
| `cleanup.ps1` | Clean up test artifacts |

## test.ps1

Main test runner for one or more Datrix projects.

### Basic Usage

```powershell
# Test a single project
.\test.ps1 datrix-common

# Test using folder path
.\test.ps1 .\datrix-common\

# Test multiple projects
.\test.ps1 datrix-common datrix-language

# Test all projects
.\test.ps1 -All
```

### Test Type Filters

```powershell
# Run only unit tests
.\test.ps1 datrix-common -Unit

# Run only integration tests
.\test.ps1 datrix-common -Integration

# Run only end-to-end tests
.\test.ps1 datrix-common -E2E

# Run fast tests (excludes slow)
.\test.ps1 datrix-common -Fast

# Run slow tests only
.\test.ps1 datrix-common -Slow
```

### Test Selection

```powershell
# Run specific test file
.\test.ps1 datrix-common -Specific "tests/unit/test_parser.py"

# Run tests matching keyword
.\test.ps1 datrix-language -Keyword "test_basic"
```

### Options

```powershell
# With coverage report
.\test.ps1 datrix-common -Coverage

# Verbose output
.\test.ps1 datrix-common -VerboseOutput

# Don't save logs
.\test.ps1 datrix-common -NoSave

# Debug mode
.\test.ps1 datrix-common -Dbg
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `-Projects` | Project names or paths (positional) |
| `-All` | Test all projects |
| `-Coverage` | Generate coverage reports |
| `-VerboseOutput` | Enable verbose test output |
| `-NoSave` | Don't save output to log files |
| `-NoAutoInstall` | Prompt for dependency installation |
| `-Unit` | Run unit tests only |
| `-Integration` | Run integration tests only |
| `-E2E` | Run end-to-end tests only |
| `-Fast` | Run fast tests only |
| `-Slow` | Run slow tests only |
| `-Specific` | Run specific test file/pattern |
| `-Keyword` | Filter tests by keyword (-k) |
| `-Dbg` | Enable debug logging |

### Output

Test results are saved to structured directories under `<project>/.test_results/`:

```
.test_results/
  test-results-20260503-191002/          # Timestamped directory per run
    index.json                           # Machine-readable index (agents read this first)
    summary.txt                          # Human-readable summary (< 50 lines)
    full.log                             # Complete pytest output
    junit-parallel.xml                   # JUnit XML from parallel phase
    junit-serial.xml                     # JUnit XML from serial phase (if applicable)
    failures/                            # One file per test failure
      001-test_module-TestClass-test_func.txt
      ...
    errors/                              # Collection/import/fixture errors
      001-import-error-test_foo.txt
      ...
```

**`index.json`** is the primary entry point for AI agents. It contains:
- Test counts (passed, failed, error, skipped)
- Per-failure details with error type, message, and source location
- Failure clusters grouped by root cause (normalized error + source location)
- Error clusters for import/fixture/collection errors

**`summary.txt`** provides a human-readable overview with cluster summaries.

**`full.log`** contains the complete pytest output (same content as the legacy flat log file).

Individual failure files in `failures/` contain the full traceback, captured stdout/stderr, and cluster assignment for a single test failure.

The test summary shows:
- Pass/fail status per project
- Test counts (passed, failed, skipped, etc.)
- AI prompt referencing `index.json` for fixing failures by cluster

## run-complete.ps1

Runs the complete test suite: generates all example projects, runs their unit tests, and produces structured test results.

```powershell
.\run-complete.ps1
```

### Generated Project Test Output

After each project's tests complete, `run_complete.py` post-processes raw test data (JUnit XML from pytest, Jest JSON from Jest) into structured result directories under each generated project's `.test_results/`:

```
{project}/.test_results/
  unit-tests-20260503-210422/
    index.json                          # Machine-readable index (agent reads this FIRST)
    summary.txt                         # Human-readable summary (< 50 lines)
    full.log                            # Combined console output
    services/
      ecommerce_user_service/
        service.log                     # Raw pytest/Jest output for this service
        junit.xml                       # (Python) pytest JUnit XML
        jest-results.json               # (TypeScript) Jest JSON report
      ecommerce_order_service/
        service.log
        junit.xml
        ...
    failures/                           # One file per unique test failure (only on failure)
      001-ecommerce_user_service-AssertionError-test_create_user.txt
      ...
    errors/                             # Collection/import errors (only on failure)
      001-ecommerce_user_service-collection-test_user_repository.txt
      ...
```

**`index.json`** is always generated (even for passing runs). **`failures/`** and **`errors/`** directories are only created when there are actual failures or errors.

**`summary.txt`** example:
```
ecommerce unit test results (TypeScript)
2026-05-03 21:04:22 | Duration: 12.3s

RESULT: FAILED (45 passed, 40 errors across 5/6 services)

.dtrx source: datrix/examples/03-domains/ecommerce/system.dtrx

ERROR CLUSTERS:
  [34 errors across 5 services] ImportError: cannot import name 'ContractViolationError' from *.errors
    Generated file: */src/*/errors/__init__.py
    Probable template: error_classes.py.j2

  [6 errors in 1 service] ImportError: cannot import name * from *._email_helpers
    Generated file: ecommerce_user_service/src/.../integrations/_email_helpers.py
    Probable template: integration_helpers.py.j2

SERVICE RESULTS:
  + ecommerce_notification_service  45 passed
  x ecommerce_user_service          9 errors
  x ecommerce_order_service         5 errors
  x ecommerce_product_service      10 errors
  x ecommerce_payment_service       7 errors
  x ecommerce_shipping_service      9 errors
```

**Individual error files** (~30 lines each) contain pre-extracted details:
```
SERVICE: ecommerce_user_service
TEST: tests/integration/repositories/test_user_repository.py
CLUSTER: ImportError: cannot import name * from *._email_helpers
ERROR: ImportError: cannot import name '_email_send_ses' from 'ecommerce_user_service.integrations._email_helpers'

--- Import Chain ---
tests/integration/repositories/test_user_repository.py:18
  -> ecommerce_user_service.services.user_db.user_service (line 19)
  -> ecommerce_user_service.integrations._email_helpers._email_send_ses (MISSING)

--- Generated File ---
ecommerce_user_service/src/ecommerce_user_service/integrations/_email_helpers.py

--- Full Traceback ---
...

--- Codegen Hint ---
Probable template: integration_helpers.py.j2
Probable generator: IntegrationGenerator
.dtrx source: datrix/examples/03-domains/ecommerce/system.dtrx
```

### Cross-Project Aggregate Index

After all projects are tested, `run_complete.py` produces a cross-project aggregate at the `.generated` level:

```
.generated/.test_results/
  unit-tests-20260503-210812/
    aggregate-index.json                # Cross-project index (agent reads this FIRST)
    aggregate-summary.txt               # Human-readable cross-project summary
    full.log                            # Full orchestration log
```

**`aggregate-summary.txt`** example:
```
Generated Project Unit Tests -- Cross-Project Summary
2026-05-03 21:08:12 | TypeScript/Docker

RESULT: 37/46 projects passed (11,661 tests passed, 52 errors)

CROSS-PROJECT CLUSTERS:
  [46 errors across 2 projects] ImportError: cannot import name 'ContractViolationError' from *.errors
    Probable template: error_classes.py.j2
    Affected: modules-imports, ecommerce

  [6 errors in 1 project] ImportError: cannot import name * from *._email_helpers
    Probable template: integration_helpers.py.j2
    Affected: ecommerce

FAILED PROJECTS:
  x modules-imports           197 passed, 12 errors  -> ContractViolationError cluster
  x ecommerce                  45 passed, 40 errors  -> ContractViolationError + _email_helpers clusters
  x advanced-cache            517 passed              -> [suiteFailure]
  ...
```

### Per-Project `index.json` Schema

```json
{
  "schema_version": 1,
  "project": "typescript/docker/03-domains/ecommerce",
  "project_path": "D:\\datrix\\.generated\\typescript\\docker\\03-domains\\ecommerce",
  "language": "typescript",
  "platform": "docker",
  "example": "03-domains/ecommerce",
  "dtrx_source": "datrix/examples/03-domains/ecommerce/system.dtrx",
  "timestamp": "2026-05-03T21:04:22",
  "duration_seconds": 12.3,
  "result": "FAILED",
  "counts": {
    "passed": 45, "failed": 0, "errors": 40, "skipped": 0, "suite_failures": 0
  },
  "services": [
    {
      "name": "ecommerce_user_service",
      "result": "FAILED",
      "counts": { "passed": 0, "failed": 0, "errors": 9, "skipped": 0, "suite_failures": 0 },
      "log_file": "services/ecommerce_user_service/service.log"
    }
  ],
  "failures": [],
  "errors": [
    {
      "id": 1,
      "service": "ecommerce_user_service",
      "test_id": "tests/integration/repositories/test_user_repository.py",
      "error_type": "ImportError",
      "error_message": "cannot import name '_email_send_ses' from '..._email_helpers'",
      "import_chain": ["test_user_repository.py -> user_service", "user_service.py -> _email_send_ses"],
      "generated_file": "ecommerce_user_service/src/.../integrations/_email_helpers.py",
      "log_file": "errors/001-ecommerce_user_service-collection-test_user_repository.txt"
    }
  ],
  "failure_clusters": [],
  "error_clusters": [
    {
      "cluster_id": 1,
      "pattern": "ImportError: cannot import name * from *._email_helpers",
      "generated_file": "ecommerce_user_service/src/.../integrations/_email_helpers.py",
      "count": 6,
      "services_affected": ["ecommerce_user_service"],
      "error_ids": [1, 2, 3, 4, 5, 6],
      "representative_error_id": 1,
      "codegen_hint": {
        "probable_template": "integration_helpers.py.j2",
        "probable_generator": "IntegrationGenerator"
      }
    }
  ]
}
```

Key fields:
- **`dtrx_source`**: Derived from the project path. Allows immediate lookup of the `.dtrx` file.
- **`import_chain`**: For collection errors, traces the import chain from the test to the missing symbol.
- **`generated_file`**: The generated file that contains the bug, derived from the error traceback.
- **`services_affected`**: Which services in this project hit this cluster.
- **`codegen_hint`**: Best-effort guess at which template/generator produced the buggy code. May be `null` if the mapping is ambiguous. Treat as a starting point, not gospel.

### Cross-Project `aggregate-index.json` Schema

```json
{
  "schema_version": 1,
  "timestamp": "2026-05-03T21:08:12",
  "language": "typescript",
  "platform": "docker",
  "total_projects": 46,
  "projects_passed": 37,
  "projects_failed": 9,
  "total_counts": {
    "passed": 11661, "failed": 0, "errors": 52, "skipped": 0, "suite_failures": 7
  },
  "failed_projects": [
    {
      "project": "typescript/docker/03-domains/ecommerce",
      "example": "03-domains/ecommerce",
      "result_dir": ".../.test_results/unit-tests-20260503-210422",
      "counts": { "passed": 45, "failed": 0, "errors": 40, "suite_failures": 0 },
      "top_cluster_pattern": "ImportError: cannot import name 'ContractViolationError' from *.errors"
    }
  ],
  "cross_project_clusters": [
    {
      "cluster_id": 1,
      "pattern": "ImportError: cannot import name 'ContractViolationError' from *.errors",
      "projects_affected": ["modules-imports", "ecommerce"],
      "total_errors": 46,
      "codegen_hint": {
        "probable_template": "error_classes.py.j2",
        "probable_generator": "ErrorGenerator"
      },
      "representative_project": "modules-imports"
    }
  ],
  "suite_failure_clusters": [
    {
      "cluster_id": 1,
      "pattern": "Cannot find module *",
      "projects_affected": ["advanced-cache", "batch-operations", "..."],
      "total_suite_failures": 7,
      "representative_project": "advanced-cache"
    }
  ]
}
```

Key fields:
- **`cross_project_clusters`**: Groups identical error patterns across projects. An agent reads this and immediately knows how many errors share one root cause across the entire test run.
- **`suite_failure_clusters`**: Environment-level issues (missing modules, config errors) that prevent an entire test suite from running. Separate from test-level errors because they have different root causes (typically missing dependencies or build issues).
- **`representative_project`**: The project to investigate first for a given cluster.
- **`top_cluster_pattern`**: Per failed-project, the most common error pattern. `null` for projects that only have suite failures (use `suite_failure_message` instead).

### Schema Evolution Policy

Both `index.json` and `aggregate-index.json` carry `schema_version: 1` as their first field.

- **Additive changes** (new optional fields): No version bump. Readers must ignore unknown fields.
- **Breaking changes** (field renamed, type changed, required field added, field removed): Bump `schema_version`.
- **Reader behavior**: Read `schema_version` first. If the version is higher than the reader supports, log a warning and fall back to reading `summary.txt`. Never reject the file.
- **Writer behavior**: Always write the current schema version. No multi-version output.

### Agent Workflow

With structured output, an agent investigating generated test failures follows this workflow:

1. Read `aggregate-index.json` — see all failed projects, cross-project clusters, codegen hints
2. Read representative project's `index.json` — full per-service breakdown, error clusters with import chains
3. Read `errors/001-....txt` (~30 lines) — understand one representative error per cluster
4. Fix root cause in template/generator — re-run — read new `aggregate-index.json`

This replaces the previous workflow of reading the summary log, then each per-service log (~150 lines each), then manually grouping errors across services and projects.

## status-tests.ps1

Shows a summary of test status across projects.

```powershell
.\status-tests.ps1
```

## compare-tests.ps1

Compares timestamped test result folders inside one project's `.test_results` directory.
Unlike the status scripts, this command does not scan multiple projects. Pass the exact
`.test_results` folder for the generated or package project you want to inspect.

```powershell
.\compare-tests.ps1 D:\datrix\.projects\curvaero\python\.test_results
```

It compares run types separately:

- `unit-tests-*` folders are compared only with other `unit-tests-*` folders.
- `deploy-test-*` folders are compared only with other `deploy-test-*` folders.
- When more than two matching folders exist, all runs are listed and the service-level
  delta compares the second-newest run to the newest run.
- The history column shows each service's status across all discovered runs.

Write a Markdown report with `-Report`:

```powershell
.\compare-tests.ps1 D:\datrix\.projects\curvaero\python\.test_results -Report D:\datrix\curvaero-test-comparison.md
```

### Parameters

| Parameter | Description |
|-----------|-------------|
| `-TestResults` | Path to a single `.test_results` folder (positional, required) |
| `-Report` | Optional Markdown report output path |
| `-Dbg` | Enable debug logging |

## cleanup.ps1

Cleans up test result directories under `.test_results/`. Supports full deletion (`-Force`) and trimming to keep the N most recent runs (`-Force -Trim`).

```powershell
# List what would be deleted (dry run)
.\cleanup.ps1

# Delete all test results
.\cleanup.ps1 -Force

# Keep 10 newest runs, delete older
.\cleanup.ps1 -Force -Trim
```
