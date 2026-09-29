---
description: Diagnose and fix datrix-semantic test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Semantic

Diagnose and fix failures, errors, and warnings in `datrix-semantic` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-semantic D:\datrix\datrix-semantic\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-semantic`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-semantic\`

## Package Specifics

- **Scope:** `datrix-semantic` — semantic analysis: `SemanticAnalyzer` and its declared phase pipeline, every domain validator, synthesis, auth-contract lowering.
- **Fix target:** Source code or test code.
- **Boundary:** depends on `datrix-common` only. A fix must never import the parser (`datrix_language`), the CLI, or a codegen package. Test inputs are built with `datrix-testing` factories, not by parsing through the language package.
- **Validators fail closed:** a failing validator test is evidence about the validator or the input, not permission to relax the rule. Never weaken, skip, or exempt a validation — especially an auth-contract or permission check — to turn a test green (execution-contract §13).
- **CAUTION:** Consumed by `datrix-language`, `datrix-cli`, `datrix-testing`, and `datrix-codegen-azure`. A changed diagnostic code, message, or validation outcome reaches every one of them. Flag any public-contract change and run the changed behaviour's feature tags in every consuming package it reaches (never a whole suite).
