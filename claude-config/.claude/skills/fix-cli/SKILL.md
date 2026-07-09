---
description: Diagnose and fix datrix-cli test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix CLI

Diagnose and fix failures, errors, and warnings in `datrix-cli` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-cli D:\datrix\datrix-cli\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-cli`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-cli\`

## Package Specifics

- **Scope:** `datrix-cli` — CLI tool.
- **Fix target:** Source code or test code — never generated output.
