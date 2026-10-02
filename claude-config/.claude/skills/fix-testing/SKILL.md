---
description: Diagnose and fix datrix-testing test failures, errors, and warnings from structured test results
model: claude-sonnet-5-5
effort: medium
---

# Fix Testing

Diagnose and fix failures, errors, and warnings in `datrix-testing` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-testing D:\datrix\datrix-testing\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-testing`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-testing\`

## Package Specifics

- **Scope:** `datrix-testing` — the shared test harness: real-AST factories, fixtures, assertions, `.dtrx` parsing helpers, determinism and semantic-baseline harnesses.
- **Fix target:** Source code or test code.
- **Boundary:** depends on `datrix-common`, `datrix-semantic`, and `datrix-codegen-kernel`. It is a `dev` extra of every package, never a runtime dependency. The `pytest11` feature-tag plugin lives in `datrix-common`, not here — a feature-tag collection failure is a `/fix-common` handoff.
- **Real objects only:** the harness exists so tests use real ASTs. Never add a mock, `SimpleNamespace`, or fake to a factory or fixture.
- **CAUTION:** Every package's test suite imports this harness. A changed factory default, fixture shape, or assertion helper can move tests in any package. Flag any public-contract change and run the changed behaviour's feature tags in every consuming package it reaches (never a whole suite).
