---
description: Diagnose and fix datrix-common test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Common

Diagnose and fix failures, errors, and warnings in `datrix-common` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-common D:\datrix\datrix-common\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-common`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-common\`

## Package Specifics

- **Scope:** shared framework library — fix source code or test code.
- **CAUTION:** Changes to datrix-common can affect ALL downstream packages (every generator consumes it). Be especially careful with API changes; per CLAUDE.md's cross-surface impact rule, flag any public-contract change so consuming packages' suites can be run.
