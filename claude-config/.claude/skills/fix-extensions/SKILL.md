---
description: Diagnose and fix datrix-extensions test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Extensions

Diagnose and fix failures, errors, and warnings in `datrix-extensions` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-extensions D:\datrix\datrix-extensions\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-extensions`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-extensions\`

## Package Specifics

- **Scope:** `datrix-extensions` — extensions package.
- **Fix target:** Source code or test code.
