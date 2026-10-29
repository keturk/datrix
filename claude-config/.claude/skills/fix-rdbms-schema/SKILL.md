---
description: Diagnose and fix datrix-rdbms-schema test failures, errors, and warnings from structured test results
model: claude-sonnet-5-5
effort: high
---

# Fix RDBMS Schema

Diagnose and fix failures, errors, and warnings in `datrix-rdbms-schema` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-rdbms-schema D:\datrix\datrix-rdbms-schema\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-rdbms-schema`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-rdbms-schema\`

## Package Specifics

- **Scope:** `datrix-rdbms-schema` — RDBMS schema machinery: canonical schema snapshot, schema diff, change policy, convergence planner, SQL lowering, catalog reader.
- **Fix target:** Source code or test code. A failing declarative case (`tests/test_cases.py::test_case[<area>::<case-id>]`) is fixed in product code, or by a person correcting the authored expectation in review — never by writing a code test for the same fact (`guard-code-standards.py` refuses one).
- **Boundary:** depends on `datrix-common` only. Dialect-specific rendering lives in the RDBMS-emitting generators and the kernel's SQL dialect facts, never here — a fix must not add a dialect or generator import.
- **Data safety:** the change policy decides which schema changes are destructive. Never loosen it (reclassify a destructive change as safe, drop a guard) to turn a test green — that is a weakened control (execution-contract §13).
- **CAUTION:** Consumed by `datrix-cli`, `datrix-codegen-common`, and the python, typescript, and sql generators. Flag any public-contract change and run the changed behaviour's feature tags in every consuming package it reaches (never a whole suite).
