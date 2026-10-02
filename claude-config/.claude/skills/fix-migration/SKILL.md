---
description: Diagnose and fix datrix-migration test failures, errors, and warnings from structured test results
model: claude-sonnet-5-5
effort: medium
---

# Fix Migration

Diagnose and fix failures, errors, and warnings in `datrix-migration` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-migration D:\datrix\datrix-migration\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-migration`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-migration\`

## Package Specifics

- **Scope:** `datrix-migration` — RDBMS migration machinery: canonical schema snapshot, schema diff, change policy, revision ledger and ids, rebaseline, live-snapshot artifact, migration state store.
- **Fix target:** Source code or test code.
- **Boundary:** depends on `datrix-common` only. Dialect-specific rendering lives in the RDBMS-emitting generators and the kernel's SQL dialect facts, never here — a fix must not add a dialect or generator import.
- **Data safety:** the change policy decides which schema changes are destructive. Never loosen it (reclassify a destructive change as safe, drop a guard) to turn a test green — that is a weakened control (execution-contract §13).
- **CAUTION:** Consumed by `datrix-cli`, `datrix-codegen-common`, and the python, typescript, and sql generators. Flag any public-contract change and run the changed behaviour's feature tags in every consuming package it reaches (never a whole suite).
