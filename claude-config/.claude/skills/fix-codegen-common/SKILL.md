---
description: Diagnose and fix datrix-codegen-common test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Codegen Common

Diagnose and fix failures, errors, and warnings in `datrix-codegen-common` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-common D:\datrix\datrix-codegen-common\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-common`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-common\`

## Package Specifics

- **Scope:** `datrix-codegen-common` — shared codegen library.
- **Fix target:** Source code or test code — never generated output.
- **CAUTION:** Shared by every codegen package (per CLAUDE.md's cross-surface impact rule). Flag any public-contract change so consuming packages' suites can be run.
