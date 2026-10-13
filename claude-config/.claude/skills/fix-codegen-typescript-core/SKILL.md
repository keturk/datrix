---
description: Diagnose and fix datrix-codegen-typescript-core test failures, errors, and warnings from structured test results
model: claude-sonnet-5-5
effort: high
---

# Fix Codegen TypeScript Core

Diagnose and fix failures, errors, and warnings in `datrix-codegen-typescript-core` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-typescript-core D:\datrix\datrix-codegen-typescript-core\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-typescript-core`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-typescript-core\`

## Package Specifics

- **Scope:** `datrix-codegen-typescript-core` — the shared TypeScript language core: transpiler core and visitors, language profile, type maps and resolver, TypeScript naming and path facts, web-client mechanics. A library with no entry point.
- **Fix target:** Source code or test code — never generated output. A failing declarative case (`tests/test_cases.py::test_case[<area>::<case-id>]`: a row, or an annotation such as `// @emits <expression>` on a fixture line) is fixed in product code, or by a person correcting the authored expectation or annotation in review — never by writing a code test for the same fact (`guard-code-standards.py` refuses one).
- **Boundary:** depends on `datrix-common`, `datrix-codegen-kernel`, and `datrix-codegen-common` only (import-linter contract + fresh-subprocess test that imports each module first). A fix must never import `datrix_codegen_typescript` (the backend) or any frontend target such as `datrix_codegen_angular` — those depend on this package, not the reverse.
- **CAUTION:** Consumed by the TypeScript backend (`datrix-codegen-typescript`) and every frontend target that emits TypeScript (`datrix-codegen-angular` today). Flag any public-contract change and run the changed behaviour's feature tags in every consuming package it reaches (never a whole suite).
