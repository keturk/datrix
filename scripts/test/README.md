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

### Deploy Test Structured Output

Deploy tests verify that generated projects build, deploy, and pass spec/integration tests against real Docker containers. After each project's deploy tests complete, `run_complete.py` post-processes raw test data (failures.json, JUnit XML, Jest JSON, Docker logs, deploy-test-output.log) into structured result directories under each generated project's `.test_results/`:

```
{project}/.test_results/
  deploy-test-20260503-210903/
    index.json                       # Machine-readable index (agent reads this FIRST)
    summary.txt                      # Human-readable summary (< 60 lines)
    full.log                         # Combined execution log
    environment.json                 # Toolchain metadata
    docker-logs/                     # Per-container logs (unchanged)
      library_book_service.log
      library_book_service-book-db-db.log
      ...
    services/
      library_book_service/
        spec/
          junit.xml                  # (Python) pytest JUnit XML for spec tests
          jest-results.json          # (TypeScript) Jest JSON for spec tests
        integration/
          junit-project.xml          # (Python) project-level integration tests
          junit-service.xml          # (Python) per-service integration tests
          jest-results.json          # (TypeScript) Jest JSON for integration tests
    failures/                        # One file per unique test failure (logic only)
      001-library_book_service-spec-AssertionError-book_validation.txt
      ...
    errors/                          # Infrastructure/lifecycle errors
      001-docker-up-container-unhealthy.txt
      002-health-check-timeout-library_book_service.txt
      ...
```

**`index.json`** is always generated (even for passing runs). **`failures/`** and **`errors/`** directories are only created when there are actual failures or errors.

#### Deploy Test Phases

Deploy tests progress through distinct phases. Failures at each phase have different characteristics:

| Phase | What happens | Failure output |
|-------|-------------|---------------|
| **docker-build** | `docker compose build` | Exit code + build output in `full.log` |
| **docker-up** | `docker compose up -d` + wait for healthy | Exit code + container logs in `docker-logs/` |
| **health-check** | HTTP health check per service | Timeout/error in `full.log` + container logs |
| **db-connectivity** | Database URL resolution + connection test | Error in `full.log` |
| **spec-tests** | pytest/Jest spec tests per service | `failures.json` + JUnit XML / Jest JSON |
| **integration-tests** | pytest/Jest integration tests | `failures.json` + JUnit XML / Jest JSON |

The `index.json` captures which phase failed, enabling agents to immediately distinguish Docker lifecycle issues from test failures.

#### Example summary.txt (Infrastructure Failure)

```
cache deploy test results (Python)
2026-05-03 21:10:03 | Duration: 120.5s

RESULT: FAILED at docker-up phase

.dtrx source: datrix/examples/02-features/03-infrastructure-blocks/cache/system.dtrx

PHASES:
  ✓ docker-build    13.2s
  ✗ docker-up       75.0s  → ContainerUnhealthy: library-book-service is unhealthy
  - health-check    (skipped)
  - db-connectivity (skipped)
  - spec-tests      (skipped)
  - integration     (skipped)

ERRORS:
  [docker-up] ContainerUnhealthy: dependency failed to start: container library-book-service is unhealthy
    Container log: docker-logs/library-book-service.log
    Probable template: docker-compose.yml.j2

SERVICE STATUS:
  ✗ library_book_service  port:8000  docker:unhealthy  tests:skipped
```

#### Example summary.txt (Test Failures)

```
01-foundation deploy test results (Python)
2026-05-03 21:09:03 | Duration: 87.3s

RESULT: FAILED at integration-tests phase (17 passed, 2 failed)

.dtrx source: datrix/examples/01-foundation/system.dtrx

PHASES:
  ✓ docker-build    13.2s
  ✓ docker-up       60.0s
  ✓ health-check     0.5s
  ✓ db-connectivity   0.2s
  ✓ spec-tests        3.5s  (all passed)
  ✗ integration      10.0s  (17 passed, 2 failed)

FAILURE CLUSTERS:
  [1 logic failure] AssertionError: assert * == response.status_code
    Probable template: test_service.py.j2

  [1 transient failure] ConnectionResetError: *
    (transient — likely infrastructure flakiness, not a codegen bug)

SERVICE STATUS:
  ✓ library_book_service  port:8000  docker:healthy  spec:passed  integration:FAILED (2)
```

#### Individual Error Files

**Infrastructure error:** `errors/001-docker-up-container-unhealthy.txt`

```
PHASE: docker-up
ERROR: ContainerUnhealthy
MESSAGE: dependency failed to start: container library-book-service is unhealthy

--- Relevant Container ---
library-book-service

--- Container Log Excerpt ---
(last 50 lines of docker-logs/library-book-service.log)
INFO library_book_service.main application_starting service=library_book_service
ERROR library_book_service.cache.redis_client redis_connection_failed host=library-book-service-cache port=6379
ERROR library_book_service.main startup_failed error=Cannot connect to Redis at library-book-service-cache:6379
...

--- Generated Files ---
docker-compose.yml
library_book_service/Dockerfile

--- Codegen Hint ---
Probable template: docker-compose.yml.j2
Probable generator: DockerComposeGenerator
.dtrx source: datrix/examples/02-features/03-infrastructure-blocks/cache/system.dtrx
```

**Test failure:** `failures/001-library_book_service-integration-AssertionError-test_create_book.txt`

```
SERVICE: library_book_service
PHASE: integration-tests
TEST: tests/test_library_book_service.py::TestLibraryBookServiceService::test_create_book
FAILURE TYPE: logic
ERROR: AssertionError: assert 201 == response.status_code, got 400

--- Traceback ---
tests/test_library_book_service.py:42: in test_create_book
    assert response.status_code == 201, f"Expected 201, got {response.status_code}"
AssertionError: assert 201 == response.status_code, got 400

--- Generated File ---
tests/test_library_book_service.py

--- Codegen Hint ---
Probable template: test_service.py.j2
Probable generator: IntegrationTestGenerator
.dtrx source: datrix/examples/01-foundation/system.dtrx
```

#### Cross-Project Aggregate Index (Deploy Tests)

After all projects are tested, `run_complete.py` produces a cross-project aggregate at the `.generated` level:

```
.generated/.test_results/
  deploy-tests-20260503-210903/
    aggregate-index.json             # Cross-project index (agent reads this FIRST)
    aggregate-summary.txt            # Human-readable cross-project summary
    full.log                         # Full orchestration log
```

**`aggregate-summary.txt`** example:

```
Generated Project Deploy Tests — Cross-Project Summary
2026-05-03 21:30:16 | Python/Docker

RESULT: 10/12 projects passed (180 tests passed, 2 failed)

INFRASTRUCTURE FAILURES (1 project):
  ✗ cache  → docker-up: ContainerUnhealthy (library-book-service)
    Probable template: docker-compose.yml.j2

LOGIC FAILURES (1 project):
  ✗ 01-foundation  → integration: AssertionError: assert * == response.status_code
    Probable template: test_service.py.j2

TRANSIENT FAILURES:
  ✗ 01-foundation  → integration: ConnectionResetError (1 test)

PASSED PROJECTS (10):
  ✓ entities            20 passed
  ✓ authentication      18 passed
  ✓ rest-api            18 passed
  ...
```

#### Per-Project index.json Schema (Deploy Tests)

```json
{
  "schema_version": 1,
  "project": "python/docker/02-features/03-infrastructure-blocks/cache",
  "project_path": "D:\\datrix\\.generated\\python\\docker\\02-features\\03-infrastructure-blocks\\cache",
  "language": "python",
  "platform": "docker",
  "example": "02-features/03-infrastructure-blocks/cache",
  "dtrx_source": "datrix/examples/02-features/03-infrastructure-blocks/cache/system.dtrx",
  "timestamp": "2026-05-03T21:10:03",
  "duration_seconds": 120.5,
  "result": "FAILED",
  "failed_phase": "docker-up",
  "phases": {
    "docker-build": { "result": "PASSED", "duration_seconds": 13.2 },
    "docker-up": {
      "result": "FAILED",
      "duration_seconds": 75.0,
      "error_message": "dependency failed to start: container library-book-service is unhealthy",
      "relevant_containers": ["library-book-service"]
    },
    "health-check": { "result": "SKIPPED" },
    "db-connectivity": { "result": "SKIPPED" },
    "spec-tests": { "result": "SKIPPED" },
    "integration-tests": { "result": "SKIPPED" }
  },
  "services": [
    {
      "name": "library_book_service",
      "port": 8000,
      "docker_healthy": false,
      "health_check_passed": false,
      "db_connectivity_passed": false,
      "spec_result": "SKIPPED",
      "integration_result": "SKIPPED",
      "counts": { "passed": 0, "failed": 0, "errors": 0, "skipped": 0 }
    }
  ],
  "failures": [],
  "errors": [
    {
      "id": 1,
      "phase": "docker-up",
      "error_type": "ContainerUnhealthy",
      "error_message": "dependency failed to start: container library-book-service is unhealthy",
      "container": "library-book-service",
      "docker_log_file": "docker-logs/library-book-service.log",
      "log_file": "errors/001-docker-up-container-unhealthy.txt",
      "generated_file": "docker-compose.yml",
      "codegen_hint": {
        "probable_template": "docker-compose.yml.j2",
        "probable_generator": "DockerComposeGenerator"
      }
    }
  ],
  "failure_clusters": [],
  "error_clusters": [
    {
      "cluster_id": 1,
      "pattern": "ContainerUnhealthy: * is unhealthy",
      "phase": "docker-up",
      "count": 1,
      "services_affected": ["library_book_service"],
      "error_ids": [1],
      "representative_error_id": 1,
      "codegen_hint": {
        "probable_template": "docker-compose.yml.j2",
        "probable_generator": "DockerComposeGenerator"
      }
    }
  ]
}
```

Key fields:
- **`failed_phase`**: The first phase that failed. Allows the agent to immediately know whether this is a Docker lifecycle issue or a test issue.
- **`relevant_containers`**: For Docker lifecycle errors, which containers are involved. The agent reads only these docker log files.
- **`failure_type`**: `"transient"` (infrastructure issues like connection resets, timeouts) or `"logic"` (actual bugs). Agents focus on `"logic"` failures for codegen fixes.
- **`phases`**: Ordered progression. Later phases are `SKIPPED` if an earlier phase failed.

#### Cross-Project aggregate-index.json Schema (Deploy Tests)

```json
{
  "schema_version": 1,
  "timestamp": "2026-05-03T21:30:16",
  "language": "python",
  "platform": "docker",
  "total_projects": 12,
  "projects_passed": 10,
  "projects_failed": 2,
  "total_counts": {
    "passed": 180,
    "failed": 2,
    "errors": 0,
    "skipped": 0,
    "infrastructure_failures": 1
  },
  "failed_projects": [
    {
      "project": "python/docker/02-features/03-infrastructure-blocks/cache",
      "example": "02-features/03-infrastructure-blocks/cache",
      "result_dir": "D:\\datrix\\.generated\\python\\docker\\02-features\\03-infrastructure-blocks\\cache\\.test_results\\deploy-test-20260503-210903",
      "failed_phase": "docker-up",
      "counts": { "passed": 0, "failed": 0, "errors": 0 },
      "top_cluster_pattern": "ContainerUnhealthy: * is unhealthy"
    },
    {
      "project": "python/docker/01-foundation",
      "example": "01-foundation",
      "result_dir": "D:\\datrix\\.generated\\python\\docker\\01-foundation\\.test_results\\deploy-test-20260503-210903",
      "failed_phase": "integration-tests",
      "counts": { "passed": 17, "failed": 2, "errors": 0 },
      "top_cluster_pattern": "AssertionError: assert * == response.status_code"
    }
  ],
  "cross_project_clusters": [
    {
      "cluster_id": 1,
      "pattern": "ContainerUnhealthy: * is unhealthy",
      "phase": "docker-up",
      "failure_type": "infrastructure",
      "projects_affected": ["02-features/03-infrastructure-blocks/cache"],
      "total_errors": 1,
      "codegen_hint": {
        "probable_template": "docker-compose.yml.j2",
        "probable_generator": "DockerComposeGenerator"
      },
      "representative_project": "02-features/03-infrastructure-blocks/cache"
    },
    {
      "cluster_id": 2,
      "pattern": "AssertionError: assert * == response.status_code",
      "phase": "integration-tests",
      "failure_type": "logic",
      "projects_affected": ["01-foundation"],
      "total_errors": 1,
      "codegen_hint": {
        "probable_template": "test_service.py.j2",
        "probable_generator": "IntegrationTestGenerator"
      },
      "representative_project": "01-foundation"
    }
  ]
}
```

Key fields:
- **`infrastructure_failures`**: Count of projects that failed in Docker lifecycle phases (never reached tests). Distinct from test-level failures.
- **`failed_phase`**: Per project, the phase that failed. Enables quick scanning: "3 projects failed at docker-up, 2 at integration-tests."
- **`failure_type`**: At the cluster level, distinguishes `"infrastructure"` (Docker lifecycle), `"logic"` (codegen bug), and `"transient"` (environment flakiness). Agents prioritize `"logic"` clusters.

#### Transient Error Patterns

Python deploy tests classify failures as `"transient"` (infrastructure/environment issues) or `"logic"` (actual bugs) at runtime. TypeScript failures are classified during post-processing. The transient patterns are defined in `datrix/scripts/library/shared/deploy_test_log_writer.py` as `TRANSIENT_ERROR_PATTERNS` and include:

- Connection-related: `ConnectionResetError`, `ConnectionDoesNotExistError`, `connection was closed in the middle of operation`
- Network/DNS: `getaddrinfo failed`, `Name or service not known`, `Temporary failure in name resolution`
- Timeout: `timeout`, `timed out`
- Database: `server closed the connection unexpectedly`, `connection to server * closed unexpectedly`
- Infrastructure: `Cannot connect to`, `Connection refused`, `No route to host`

Agents skip transient failures when investigating codegen bugs, as they indicate environment issues rather than code generation problems.

#### Agent Workflow (Deploy Tests)

With structured output, an agent investigating generated deploy test failures follows this workflow:

1. Read `aggregate-index.json` — see all failed projects, phases, cross-project clusters, codegen hints
2. Read representative project's `index.json` — full phase breakdown, service status, error/failure clusters
3. Read `errors/001-....txt` or `failures/001-....txt` (~30 lines) — understand the error with relevant container log excerpt
4. Fix root cause in template/generator — re-run — read new `aggregate-index.json`

This replaces the previous workflow of reading deploy-test-summary.log (minimal detail), deploy-test-output.log (~200 lines), failures.json (flat list), and guessing which of 10-20 docker container logs (~100KB total) to read.

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
