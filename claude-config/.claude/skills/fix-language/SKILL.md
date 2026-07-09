---
description: Diagnose and fix datrix-language test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Language

Diagnose and fix failures, errors, and warnings in `datrix-language` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-language D:\datrix\datrix-language\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-language`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-language\`

## Package Specifics

- **Scope:** `datrix-language` — DSL parser and language package.
- **Fix target:** Parser, transformer, validator, or test code.
- **CAUTION:** Changes to datrix-language affect ALL downstream packages that parse .dtrx files. Be especially careful with grammar and AST changes.
