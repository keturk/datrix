---
description: Diagnose and fix datrix-codegen-azure test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Codegen Azure

Diagnose and fix failures, errors, and warnings in `datrix-codegen-azure` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-azure D:\datrix\datrix-codegen-azure\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-azure`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-azure\`

## Package Specifics

- **Scope:** `datrix-codegen-azure` — Azure infrastructure codegen.
- **Fix target:** Generator source code, templates, or test code — never generated output.
