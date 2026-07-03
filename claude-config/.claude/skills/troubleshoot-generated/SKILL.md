---
model: claude-opus-4-8
---

# Troubleshoot Generated Code Skill

**Reasoning effort: HIGH.** Apply STOP AND THINK throughout — trace the full causal chain from symptom to codegen root cause before writing anything. Read the generator/template/transformer and the offending `.dtrx` source before forming a hypothesis. One correctly diagnosed root cause beats five plausible-sounding guesses.

Diagnose failures in generated code tests, trace errors back to Datrix codegen sources (templates, generators, .dtrx files), and produce a detailed timestamped situation report under `d:\datrix\issues`.

**This skill does NOT fix issues.** It investigates, documents, and reports. No quick fixes, no hacks, no workarounds — only thorough diagnosis and honest documentation.

## When to Use

- User reports test failures in generated code (unit_tests.py or deploy_test.py)
- User asks to "troubleshoot", "debug", or "diagnose" generated code tests
- User points to a `.test_results/` folder with failures
- User mentions a generated project has failing tests or broken containers

## How to Invoke

The primary invocation is with **LOG FOLDERS** — one or more paths to test result folders that contain failures:

```
/troubleshoot-generated

LOG FOLDERS:
D:\datrix\.generated\python\docker\02-features\05-infrastructure-combinations\multi-database\.test_results\deploy-test-20260303-111315
D:\datrix\.generated\python\docker\02-features\01-core-data-modeling\relationships\.test_results\unit-tests-20260303-120045
```

Single folder:
```
/troubleshoot-generated

LOG FOLDER:
D:\datrix\.generated\python\docker\01-foundation\.test_results\unit-tests-20260303-111307
```

Alternative invocations (skill resolves the log folders):
```
"Troubleshoot generated tests for 01-basic-entity"
"Diagnose failing tests in .generated/python/docker/02-features/05-infrastructure-combinations/multi-database"
```

## Documentation Quick Reference

For complete documentation index with "When to use" guidance, see [doc_index.md](../../../../../datrix/docs/doc_index.md).

**Essential reads (MANDATORY before starting):**
- [ai-agent-rules.md](../../../../../datrix-common/docs/contributing/ai-agent-rules.md) → Core rules, STOP AND THINK principle
- [architecture-overview.md](../../../../../datrix/docs/architecture/architecture-overview.md) → System architecture
- [design-principles.md](../../../../../datrix/docs/architecture/design-principles.md) → Design philosophy

**Quick refs:**
- [architecture-cheat-sheet.md](../../../../../datrix/docs/architecture/architecture-cheat-sheet.md)
- [design-principles-cheat-sheet.md](../../../../../datrix/docs/architecture/design-principles-cheat-sheet.md)

### Project Structure
Read `d:\datrix\{package-name}\.project-structure.md`. Regenerate if missing: `powershell -File "d:/datrix/datrix/scripts/dev/project-structure.ps1" {package-name}`.

## Scope Check (BEFORE starting investigation)

After reading mandatory documents and BEFORE any investigation, assess the scope:

1. **Count the log folders provided** — each folder is a potential multi-hour investigation
2. **Check if log folders span different languages/platforms** — Python + TypeScript failures are separate investigations
3. **Check if the failures are in different subsystems** — a template bug vs a Docker config bug vs a runtime crash are separate issues

**If the scope is too large** (more than 2-3 distinct failure categories, or spanning multiple languages), STOP and tell the user:

```
This investigation spans [N] distinct failure areas. I recommend splitting into separate sessions:

1. [First focused investigation] — [which log folders]
2. [Second focused investigation] — [which log folders]

Which should I start with?
```

**Do NOT silently attempt to investigate everything.** A thorough investigation of one issue is infinitely more valuable than a shallow pass over five issues.

## STOP AND THINK

**Before writing anything, understand the problem fully.** Do not guess. Do not jump to conclusions. Trace the full causal chain from symptom to root cause.

Before writing the report:
1. **Read and understand** all relevant code — generated code, templates, generators, .dtrx source
2. **Trace the root cause** — why is this happening, not just what is happening
4. **If uncertain, say so** — never guess at architecture, intent, or behavior

## Inputs

The user provides **LOG FOLDERS** — one or more paths to test result directories containing failure logs.

**Each log folder is either:**
- A `unit-tests-*` folder (from `unit_tests.py` — unit tests, no Docker)
- A `deploy-test-*` folder (from `deploy_test.py` — Docker deployment + integration tests)

**The log folder path encodes everything needed to locate the generated project:**
```
D:\datrix\.generated\python\docker\02-features\05-infrastructure-combinations\multi-database\.test_results\deploy-test-20260303-111315
│                      │      │       │              │                    │                │              └── timestamp
│                      │      │       │              │                    │                └── test type (unit-tests or deploy-test)
│                      │      │       │              │                    └── example name
│                      │      │       │              └── subcategory
│                      │      │       └── category
│                      │      └── platform
│                      └── language
└── generated root
```

**From this path, derive:**
- **Generated project root:** Everything before `.test_results/` (e.g., `D:\datrix\.generated\python\docker\02-features\05-infrastructure-combinations\multi-database`)
- **Test type:** `unit-tests-*` = unit tests, `deploy-test-*` = deploy tests
- **.dtrx source:** `D:\datrix\datrix\examples\{category}\{example}\` (e.g., `datrix\examples\02-features\05-infrastructure-combinations\multi-database\`)

**Alternative inputs (if no log folder given):**
1. **Generated project path** — Skill finds the latest test results under `.test_results/`
2. **Example name** — Skill resolves full path (e.g., `multi-database` → `.generated/python/docker/02-features/05-infrastructure-combinations/multi-database`)

**When multiple log folders are provided**, process them all. Failures across projects may share a common root cause (same template/generator bug) — look for patterns.

### Structured Output Directory Layout (when available)

Test results directories produced by `run_complete.py` may contain structured output:

**Unit tests:**
```
{project}/.test_results/unit-tests-{timestamp}/
  index.json                          # Machine-readable index (READ THIS FIRST)
  summary.txt                         # Human-readable summary (< 50 lines)
  full.log                            # Combined console output
  services/
    {service_name}/
      service.log                     # Raw pytest/Jest output for this service
      junit.xml                       # (Python) pytest JUnit XML
      jest-results.json               # (TypeScript) Jest JSON report
  failures/                           # One file per unique test failure
    001-{service}-{error_type}-{id}.txt
  errors/                             # One file per collection/import error
    001-{service}-{error_type}-{id}.txt
```

**Deploy tests:**
```
{project}/.test_results/deploy-test-{timestamp}/
  index.json                          # Machine-readable index (READ THIS FIRST)
  summary.txt                         # Human-readable summary (< 60 lines)
  deploy-test-output.log              # Full execution log (unchanged)
  environment.json                    # Toolchain metadata (unchanged)
  docker-logs/                        # Per-container logs (unchanged)
    library-book-service.log
    ...
  services/
    {service_name}/
      spec/
        junit.xml                     # (Python) spec test results
        jest-results.json             # (TypeScript) spec test results
      integration/
        junit-project.xml             # (Python) project-level integration
        junit-service.xml             # (Python) per-service integration
        jest-results.json             # (TypeScript) integration results
  failures/                           # One file per test failure (logic + transient)
    001-{service}-{phase}-{error_type}-{test_name}.txt
  errors/                             # Infrastructure/lifecycle errors
    001-{phase}-{error_type}[-{container}].txt
```

Cross-project aggregates (at `.generated/.test_results/`):
```
.generated/.test_results/unit-tests-{timestamp}/
  aggregate-index.json                # Cross-project unit test index
  aggregate-summary.txt

.generated/.test_results/deploy-tests-{timestamp}/
  aggregate-index.json                # Cross-project deploy test index (READ THIS FIRST)
  aggregate-summary.txt               # Grouped by infrastructure/logic/transient
  full.log                            # Full orchestration log
```

## Workflow — Phased with Confidence Checks

**This workflow is broken into phases. At the end of each phase, assess your confidence. If confident in findings, proceed to the next phase (include a brief status note). If NOT confident, STOP and present findings to the user and WAIT for their go-ahead.** Always stop when uncertain — never guess your way through a phase.

### Phase 0: Check for Structured Output

**Goal:** Determine whether structured data is available and which test type (unit or deploy).

Before reading any logs, check if the test results directory contains structured output:

1. **Identify test type from folder name:**
   - `unit-tests-*` folder → **Unit tests** (no Docker)
   - `deploy-test-*` folder → **Deploy tests** (Docker lifecycle + spec/integration tests)

2. **For cross-project analysis** (given `.generated/.test_results/`):
   - Unit tests: Check for `unit-tests-{ts}/aggregate-index.json`
   - Deploy tests: Check for `deploy-tests-{ts}/aggregate-index.json`

3. **For per-project analysis** (given a project's `.test_results/` folder):
   - Check for `index.json` in the test results directory

**If `index.json` or `aggregate-index.json` exists:**
- **Unit tests** → Use the **Unit Test Structured Workflow** (Phase 1S, 2S, 3S below)
- **Deploy tests** → Use the **Deploy Test Structured Workflow** (Phase 1D, 2D, 3D below)

**If NOT** (older test runs without structured output) → Use the **Legacy Workflow** (Phase 1L, 2L below).

---

### Phase 1S: Structured Triage (when `index.json` exists)

**Goal:** Understand WHAT failed using structured data. Dramatically fewer reads needed.

**For cross-project analysis (aggregate-index.json available):**
1. Read `aggregate-index.json` — immediately see:
   - How many projects passed/failed
   - `cross_project_clusters`: error patterns shared across projects, with codegen hints
   - `suite_failure_clusters`: environment-level failures (missing modules, etc.)
   - `failed_projects`: each with `top_cluster_pattern` and `suite_failure_message`
2. For the representative project of each cluster, read its `index.json` for per-service detail

**For single-project analysis (index.json available):**
1. Read `index.json` — immediately see:
   - Overall result and counts (passed/failed/errors)
   - `services`: per-service breakdown with results
   - `error_clusters`: grouped errors with normalized patterns, codegen hints, affected services
   - `failure_clusters`: grouped test failures with patterns
   - Each error/failure has `generated_file`, `import_chain`, `codegen_hint`
2. Read `summary.txt` for a quick human-readable overview

**End-of-phase assessment:**
- Number of distinct clusters (each cluster = one probable root cause)
- Which services/projects are affected per cluster
- Codegen hints available (probable template/generator)
- Whether this is an error cluster (import/collection issues) or failure cluster (assertion failures)

**If confident** → proceed to Phase 2S.
**If NOT confident** → STOP and present findings, WAIT for user direction.

---

### Phase 2S: Structured Detailed Investigation

**Goal:** Understand each cluster's root cause using pre-extracted error details.

For each error cluster in priority order (highest count first):

1. Read the **representative error file** at `errors/{NNN}-*.txt` (~30 lines each). Each file contains:
   - `SERVICE`: which service
   - `TEST`: which test file
   - `CLUSTER`: the normalized pattern
   - `ERROR`: the specific error message
   - `--- Import Chain ---`: the import chain that led to the failure (Python collection errors)
   - `--- Generated File ---`: the generated file that contains the bug
   - `--- Full Traceback ---`: complete traceback
   - `--- Codegen Hint ---`: probable template and generator

2. **Use the codegen hint** as a starting point:
   - `probable_template`: the Jinja2 template that likely produced the buggy code
   - `probable_generator`: the generator class that calls the template
   - `.dtrx source`: the .dtrx file for this project

3. **Only read `services/{name}/service.log`** if the individual error file doesn't have enough context.

**End-of-phase assessment:**
- Which generated files contain the problem
- The specific code that's wrong
- Your initial hypothesis per cluster

**If confident** → proceed to Phase 3S.
**If NOT confident** → STOP and present findings, WAIT.

---

### Phase 3S: Structured Root Cause Tracing

**Goal:** Trace from the structured data back to the codegen source.

1. **Start with `codegen_hint`** from the error cluster — the probable template and generator are pre-identified
2. Read the identified template file (e.g., `integration_helpers.py.j2`)
3. Read the identified generator class
4. **Verify** the hint is correct — does this template actually produce the broken file?
5. Trace the causal chain: `.dtrx source` → generator context → template rendering → broken output

**Skip manual file-path-to-generator mapping when codegen_hint is populated and verified.**

Proceed to Phase 4 (Impact and Report) as before.

---

### Phase 1D: Deploy Test Structured Triage (when deploy test `index.json` exists)

**Goal:** Understand WHAT failed in deploy tests using structured data.

Deploy test failures differ from unit tests — they include Docker lifecycle phases (build, up, health-check, db-connectivity) before test phases (spec-tests, integration-tests). The `failed_phase` field immediately tells you whether this is an infrastructure issue or a test bug.

**For cross-project analysis (deploy-tests aggregate-index.json available):**
1. Read `aggregate-index.json` — immediately see:
   - How many projects passed/failed
   - `cross_project_clusters`: error patterns shared across projects, with codegen hints
   - `failed_projects`: each with `failed_phase` and `top_cluster_pattern`
   - `total_counts.infrastructure_failures`: count of projects that never reached tests
2. For the representative project of each cluster, read its `index.json` for detail

**For single-project analysis (deploy test index.json available):**
1. Read `index.json` — immediately see:
   - `failed_phase`: the first phase that failed (key decision point)
   - `phases`: ordered progression with durations and error messages
   - `services`: per-service status (docker healthy, health check, test results)
   - `failures`: test-level failures with `failure_type` ("logic" vs "transient")
   - `errors`: infrastructure errors with container log references and codegen hints
   - `failure_clusters` and `error_clusters`: grouped by root cause pattern
2. Read `summary.txt` for a quick human-readable overview

**Decision tree based on `failed_phase`:**
- **Docker lifecycle failure** (`docker-build`, `docker-up`, `health-check`, `db-connectivity`) → Phase 2D-infra
- **Test failure** (`spec-tests`, `integration-tests`) → Phase 2D-test

**End-of-phase assessment:**
- Which phase failed (infrastructure vs test)
- How many clusters (each = one probable root cause)
- Whether failures are "logic" (codegen bugs) or "transient" (infrastructure flakiness)

**If confident** → proceed to Phase 2D.
**If NOT confident** → STOP and present findings, WAIT for user direction.

---

### Phase 2D: Deploy Test Structured Detailed Investigation

**Goal:** Understand the root cause using deploy test structured data.

#### If `failed_phase` is a Docker lifecycle phase (infrastructure failure):

1. Read the `errors/` file(s) listed in `index.json` (each ~30 lines). Each file contains:
   - `PHASE`: which Docker phase failed
   - `ERROR`: the error type and message
   - `--- Relevant Container ---`: the container that failed
   - `--- Container Log Excerpt ---`: error-grepped lines + last 50 lines from the container log
   - `--- Codegen Hint ---`: probable template and generator
2. **Only read full Docker logs from `docker-logs/`** if the excerpt is insufficient
3. Use `codegen_hint` to identify the probable template (e.g., `docker-compose.yml.j2`)

#### If `failed_phase` is a test phase (spec-tests or integration-tests):

1. Read the `failures/` file(s) listed in `index.json` (each ~30 lines). Each file contains:
   - `SERVICE`: which service
   - `PHASE`: spec-tests or integration-tests
   - `TEST`: the full test ID
   - `FAILURE TYPE`: "logic" or "transient"
   - `ERROR`: the error type and message
   - `--- Traceback ---`: full traceback
   - `--- Codegen Hint ---`: probable template and generator
2. **Focus on `failure_type: "logic"` failures** — these are codegen bugs to fix
3. **Skip `failure_type: "transient"` failures** — these are infrastructure flakiness (connection resets, timeouts), not codegen bugs
4. Use `codegen_hint.probable_template` and `codegen_hint.probable_generator` to jump to source

**End-of-phase assessment:**
- Which generated files contain the problem
- The specific code or configuration that's wrong
- Your initial hypothesis per cluster

**If confident** → proceed to Phase 3D.
**If NOT confident** → STOP and present findings, WAIT.

---

### Phase 3D: Deploy Test Structured Root Cause Tracing

**Goal:** Trace from the structured data back to the codegen source.

1. **Start with `codegen_hint`** from the error/failure — the probable template and generator are pre-identified
2. For infrastructure errors (docker-compose issues): Read the docker-compose template and DockerComposeGenerator
3. For test failures: Read the identified test template and generator
4. **Verify** the hint is correct — does this template actually produce the broken file?
5. Use `dtrx_source` from the index to find the .dtrx file that produced the failing project
6. Trace: `.dtrx source` → generator context → template rendering → broken output

**Skip manual file-path-to-generator mapping when codegen_hint is populated and verified.**

Proceed to Phase 4 (Impact and Report) as before.

---

### Phase 1L: Legacy Triage (when `index.json` does NOT exist)

**Goal:** Understand WHAT failed from raw logs. (This is the fallback for older test runs.)

**For unit-tests failures:**
1. Read `unit-tests-summary.log` — identify which services failed and how many tests failed
2. For each failed service, read `{service-name}-tests.log` — find exact test failures, assertion errors, import errors, collection errors

**For deploy-test failures:**
1. Read `deploy-test-summary.log` — identify overall status and which projects failed
2. Read `deploy-test-output.log` — find the specific failure point (build failure? health check timeout? test failure?)
3. For container issues, read `docker-logs/{container-name}.log` — find application errors, startup failures, database connection issues

**What to look for:**
- `FAILED` / `ERROR` / `ERRORS` in pytest output
- `ImportError` / `ModuleNotFoundError` — wrong imports in generated code
- `TypeError` / `AttributeError` — wrong types or missing attributes in generated code
- `SyntaxError` — template rendering produced invalid syntax
- `sqlalchemy` errors — ORM model issues
- `pydantic` validation errors — schema issues
- Health check timeouts — service startup failures (check docker logs)
- Docker build failures — missing dependencies, Dockerfile issues
- `collection errors` — pytest could not even collect the tests (import failures)

**End-of-phase assessment:**
- Which services/containers failed
- What type of failure (build, startup, test, timeout)
- Key error messages
- How many distinct failures there appear to be

**If confident** in the failure summary (clear errors, obvious patterns) → proceed to Phase 2L (include brief status note).
**If NOT confident** (ambiguous logs, unclear failure mode, too many distinct failures) → **STOP and present summary, WAIT** for user direction.

---

### Phase 2L: Legacy Read the Failing Generated Code

**Goal:** Understand the generated code that's failing. Nothing more.

From the error messages identified in Phase 1L, read the generated file(s) that contain the bug:
- Error tracebacks point to file paths within the generated project
- Map the relative path to the full generated path under `.generated/`

**Key generated file locations within a project (Python):**
```
{service_dir}/
├── src/{python_package}/
│   ├── models/{block_name}/         # SQLAlchemy ORM models
│   ├── schemas/{block_name}/        # Pydantic schemas
│   ├── services/{block_name}/       # Service layer
│   ├── routes/{block_name}/         # FastAPI routes
│   ├── events/                      # Event handlers
│   ├── cqrs/                        # CQRS components
│   ├── cache/                       # Cache configuration
│   └── config/                      # App configuration
├── tests/
├── Dockerfile
├── docker-compose.yml
└── requirements.txt
```

**Key generated file locations within a project (TypeScript):**
```
{service_dir}/
├── src/
│   ├── entities/                    # TypeORM entities
│   ├── dto/                         # Data transfer objects
│   ├── controllers/                 # NestJS controllers
│   ├── services/                    # NestJS services
│   ├── modules/                     # NestJS modules
│   ├── config/                      # Configuration files
│   ├── database/                    # Database configs
│   ├── nosql/                       # MongoDB configs
│   ├── pubsub/                      # Pub/sub configs
│   ├── observability/               # Tracing, logging
│   └── app.module.ts                # Root module
├── tests/
├── Dockerfile
├── docker-compose.yml
└── package.json
```

**End-of-phase assessment:**
- Which generated files contain the problem
- The specific code that's wrong (with line numbers)
- Your initial hypothesis about what's wrong

**If confident** in the hypothesis (clear bug, obvious mismatch) → proceed to Phase 3L (include brief status note).
**If NOT confident** (multiple possible causes, need user context on intent) → **STOP and present findings, WAIT** for user direction.

---

### Phase 3L: Legacy Trace Back to Codegen Source

**Goal:** Find the template/generator that produced the broken code.

#### 3a: Find the .dtrx Source File

The generated project path encodes the example location:
- Generated: `.generated/{language}/{platform}/{category}/{example}/`
- Source .dtrx: `datrix/examples/{category}/{example}/*.dtrx`

Read the .dtrx source to understand the entity/service definitions that drive code generation.

#### 3b: Identify the Generator and Template

Map the generated file type to its generator and template:

**Python targets:**

| Generated File Pattern | Generator Class | Template | Package |
|---|---|---|---|
| `models/{block}/*.py` | `EntityGenerator` | `entity_model.py.j2` | `datrix-codegen-python` |
| `schemas/{block}/*_schema.py` | `SchemaGenerator` | `entity_schema.py.j2` | `datrix-codegen-python` |
| `services/{block}/*_service.py` | `ServiceGenerator` | `entity_service.py.j2` | `datrix-codegen-python` |
| `routes/{block}/*_routes.py` | `EndpointGenerator` | `api_routes.py.j2` | `datrix-codegen-python` |
| `docker-compose.yml` | Docker generators | compose templates | `datrix-codegen-docker` |
| `Dockerfile` | Docker generators | dockerfile templates | `datrix-codegen-docker` |

**TypeScript targets:**

| Generated File Pattern | Generator/Template | Package |
|---|---|---|
| `src/entities/*.entity.ts` | Entity templates | `datrix-codegen-typescript` |
| `src/dto/*.dto.ts` | DTO templates | `datrix-codegen-typescript` |
| `src/config/*.ts` | Config templates | `datrix-codegen-typescript` |
| `src/database/*.ts` | Database config templates | `datrix-codegen-typescript` |
| `src/app.module.ts` | App module template | `datrix-codegen-typescript` |
| `docker-compose.yml` | Docker generators | `datrix-codegen-docker` |
| `Dockerfile` | Dockerfile templates | `datrix-codegen-docker` |

**Key source locations:**

- **Python templates:** `d:\datrix\datrix-codegen-python\src\datrix_codegen_python\templates\`
- **Python generators:** `d:\datrix\datrix-codegen-python\src\datrix_codegen_python\generators\`
- **TypeScript templates:** `d:\datrix\datrix-codegen-typescript\src\datrix_codegen_typescript\templates\`
- **TypeScript generators:** `d:\datrix\datrix-codegen-typescript\src\datrix_codegen_typescript\generators\`
- **Docker generators:** `d:\datrix\datrix-codegen-docker\src\datrix_codegen_docker\`
- **Path helpers:** `d:\datrix\datrix-common\src\datrix_common\paths.py`
- **Template engine:** `d:\datrix\datrix-common\src\datrix_common\rendering\`
- **Base generator:** `d:\datrix\datrix-common\src\datrix_common\generation\`

#### 3c: Read the Generator and Template

Read the generator class to understand:
- What context variables it passes to the template
- How it builds the context (field mappings, type resolution, path construction)
- What helper functions it calls

Read the Jinja2 template to understand:
- How the template uses the context variables
- Where the error in the generated output originates

#### 3d: Compare Generated Output vs Template

Side-by-side compare the generated code (broken) against the template logic to pinpoint exactly where the template or generator produces wrong output.

**End-of-phase assessment:**
- The specific template/generator code that causes the issue
- The causal chain from .dtrx → generator → template → broken output
- Your confidence level in the diagnosis

**If confident** in root cause (full causal chain traced, single clear origin) → proceed to Phase 4 (include brief status note). (Both structured and legacy workflows converge at Phase 4.)
**If NOT confident** (multiple possible origins, incomplete trace, need user input) → **STOP and present analysis, WAIT** for user direction.

---

### Phase 4: Group Issues and Write Report

**Goal:** Group failures and write the report.

#### 4a: Identify Distinct Issues and Group Failures

Before writing reports, **group failures by distinct technical issue**, not by example:

1. **Same root cause across multiple examples?** Create ONE report covering all affected examples
2. **Different root causes in one example?** Create SEPARATE reports
3. **How to identify distinct issues:**
   - Different templates/generators = different issues
   - Same template, different bugs = different issues
   - Same template bug manifesting in multiple examples = same issue

**The goal:** Each report documents ONE fixable problem.

#### 4b: Write the Situation Report

**DO NOT fix anything.** Instead, create a detailed timestamped report under `d:\datrix\issues`.

**Report filename format:**
```
d:\datrix\issues\YYYYMMDD-HHMMSS-{issue-slug}.md
```

Use the current date/time for the timestamp. The `{issue-slug}` should be a kebab-case description of the specific issue.

**Create one report per distinct issue**, not per example or project.

**Report template:**

```markdown
# Issue: {Short Issue Title}

**Date:** {YYYY-MM-DD HH:MM}
**Issue ID:** {YYYYMMDD-HHMMSS-issue-slug}
**Affected example(s):**
- {category}/{example-name}
- {category}/{another-example-name} (if multiple examples affected)

**Test type(s):** unit_tests / deploy_test
**Log folder(s):**
- {log folder path 1}
- {log folder path 2}

## Failure Summary

{Brief 2-3 sentence summary of what failed and how severely. If this issue affects multiple examples, explain the pattern.}

### Failed Tests

| Example | Test | Error Type | Brief Description |
|---------|------|-----------|-------------------|
| {example} | `test_module::TestClass::test_name` | TypeError | description |

### Error Details

#### In {example-name}:

**Symptom:**
```
{Key lines from the error traceback}
```

**Failing generated file:** `{path to generated file}`

**Relevant generated code:**
```
{The specific lines of generated code that are wrong, with line numbers}
```

## Root Cause Analysis

### Traced Source

| Aspect | Detail |
|--------|--------|
| **Generator** | `{GeneratorClass}` in `{file path}` |
| **Template** | `{template_name.j2}` in `{file path}` |
| **.dtrx source** | `{path to .dtrx file}` |
| **Bug location** | Template / Generator / Type mapping / AST model / Config |

### Root Cause

{Detailed explanation of WHY the failure occurs. Trace the causal chain:
1. What the .dtrx source defines
2. What the generator/template produces from that
3. Why the produced output is wrong
4. What the correct output should look like}

### Affected Code

```
# {file_path}:{line_number}
{the problematic source code}
```

## Recommended Fix

{ONLY if root cause is fully understood and fix is clear. Otherwise omit and use Open Questions.}

1. **What to change:** {specific file, specific location}
2. **How to change it:** {describe the logic change}
3. **Why this fixes it:** {causal link to root cause}
4. **What to verify after:** {tests to run, examples to regenerate}

## Open Questions

{List anything unclear. Be honest — incomplete diagnosis with acknowledged gaps is better than a confident guess.}
```

**Report quality requirements:**
- Include enough error output to understand the failure without re-reading the logs
- Include actual generated code snippets (not just file paths)
- Include actual template/generator source snippets at the identified bug location
- If multiple failures share a root cause, say so explicitly
- **No quick fixes, hacks, or workarounds**
- **Honest uncertainty** — if root cause not fully determined, say so in Open Questions

---

### Phase 5: Confirm Reports Written

After writing all reports, provide a summary:

```
Created {N} issue report(s):

1. d:\datrix\issues\YYYYMMDD-HHMMSS-{issue-slug-1}.md
   - Issue: {short title}
   - Severity: {level}
   - Affects: {N} example(s)
```

**Grouping logic:**
- Same root cause across examples = one report
- Different root causes in one example = separate reports
- One report per distinct technical issue

## Key Path Mappings

### Generated Path -> .dtrx Source
```
.generated/{language}/{platform}/{category}/{example}/  ->  datrix/examples/{category}/{example}/*.dtrx
```

### Service Directory -> Service Name
```
library_book_service  ->  library.BookService
ecommerce_order_service  ->  ecommerce.OrderService
```
Service names use dot-separated namespace + PascalCase. Service dirs use full snake_case.

### Generated File -> Template
The template that produced a file can be found by:
1. Identify the file type from its path (model, schema, service, route, test, config)
2. Look up the generator in the registry (Python: `datrix-codegen-python/.../registry.py`, TypeScript: `datrix-codegen-typescript/.../registry.py`)
3. The generator's render call specifies the template name

## CLI Quick Reference

```powershell
# Generate a single example
powershell -File d:\datrix\datrix\scripts\dev\generate.ps1 "{source.dtrx}" "{output-dir}"

# Generate all feature examples
powershell -File d:\datrix\datrix\scripts\dev\generate.ps1 -TestSet features

# Generate everything
powershell -File d:\datrix\datrix\scripts\dev\generate.ps1 -All

# Run codegen package tests
powershell -File d:\datrix\datrix\scripts\test\test.ps1 datrix-codegen-python
powershell -File d:\datrix\datrix\scripts\test\test.ps1 datrix-codegen-typescript
powershell -File d:\datrix\datrix\scripts\test\test.ps1 datrix-codegen-docker
powershell -File d:\datrix\datrix\scripts\test\test.ps1 datrix-common

# Check test status across all repos
powershell -File d:\datrix\datrix\scripts\test\status-tests.ps1

# Compile check (syntax + imports)
powershell -File d:\datrix\datrix\scripts\dev\compile.ps1 datrix-codegen-python
```

## Anti-Patterns

- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO debug scatter** — zero temporary logging statements
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
