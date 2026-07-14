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

See `d:\datrix\.claude\skills\_shared\fix-conventions.md` for the mandatory documentation reads and the Project Structure step.

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

Test results directories produced by `run_complete.py` may contain structured output (per-field detail is covered in the phases below):

- **Unit tests** (`{project}/.test_results/unit-tests-{timestamp}/`): `index.json`, `summary.txt`, `full.log`, `services/{name}/service.log` (+ `junit.xml`/`jest-results.json`), `failures/`, `errors/`
- **Deploy tests** (`{project}/.test_results/deploy-test-{timestamp}/`): `index.json`, `summary.txt`, `deploy-test-output.log`, `environment.json`, `docker-logs/`, `services/{name}/spec/` + `services/{name}/integration/`, `failures/`, `errors/`
- **Cross-project aggregates** (`.generated/.test_results/unit-tests-{timestamp}/` or `deploy-tests-{timestamp}/`): `aggregate-index.json`, `aggregate-summary.txt`, `full.log`

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
1. Run the collector and read its `failure-data.json` (read `datrix/scripts/test/quick-reference.md` first; a pre-tool hook enforces this):
   ```bash
   powershell -File "d:/datrix/datrix/scripts/test/collect-failure-data.ps1" "{test-results-dir}"
   ```
   It gives you counts, every error/failure cluster with normalized pattern, and each cluster's representative with traceback tail, `generated_file`, and `codegen_hint` — without reading `index.json`'s arrays by hand.
2. Read from `index.json` only the small top-level `services` breakdown (per-service results); skip its `failures[]`/`clusters[]` arrays

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

1. Start from the representative's `traceback_tail` already embedded in `failure-data.json`; read the full **representative error file** at `errors/{NNN}-*.txt` (~30 lines each) only if the tail lacks context. Each file contains:
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
1. Run `collect-failure-data.ps1` on the test-results dir (same invocation as Phase 1S) and read its `failure-data.json` for the clusters and representatives with traceback tails and codegen hints
2. Read from `index.json` only the deploy-specific top-level fields the collector does not re-emit:
   - `failed_phase`: the first phase that failed (key decision point)
   - `phases`: ordered progression with durations and error messages
   - `services`: per-service status (docker healthy, health check, test results)
   Skip its `failures[]`/`errors[]`/`clusters[]` arrays — they are in `failure-data.json`

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

**Goal:** Trace from the structured data back to the codegen source — trace exactly as Phase 3S, with two deploy-test-specific deltas:
- For infrastructure errors (docker-compose issues): read the docker-compose template and `DockerComposeGenerator` specifically.
- Use `dtrx_source` from the index (rather than deriving it manually) to find the .dtrx file that produced the failing project.

Proceed to Phase 4 (Impact and Report) as before.

---

### Phase 1L–3L: Legacy Triage (when `index.json` does NOT exist)

When no structured index is available (older test run), do not guess at a workflow — read and follow `d:\datrix\.claude\skills\_shared\legacy-triage.md`. It covers triage from raw logs, reading the failing generated code, and tracing back to the codegen source. Converge at Phase 4 below when confident.

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

## Anti-Patterns

- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO debug scatter** — zero temporary logging statements
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
