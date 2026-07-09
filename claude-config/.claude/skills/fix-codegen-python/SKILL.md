---
description: Diagnose and fix datrix-codegen-python test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Codegen Python

Diagnose and fix failures, errors, and warnings in `datrix-codegen-python` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-python D:\datrix\datrix-codegen-python\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-python`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-python\`

## Package Specifics

- **Scope:** Python codegen ONLY. Do NOT cross into TypeScript codegen packages.
- **Package:** `datrix-codegen-python` — Python codegen.
- **Fix target:** Generator source code, templates, transpiler, or test code — never generated output.

### Additional Test-to-Source Mapping

| Test file path | Source file path |
|---|---|
| `tests/unit/transpiler/test_operators.py` | `src/.../transpiler/operators.py` |
| `tests/transpiler/test_py_statements_coverage.py` | `src/.../transpiler/_transpiler_statements.py` + `_transpiler_expressions.py` |

### Trace Failures to Source (generator/transpiler specifics)

- For generator tests: generator function → template context → template rendering
- For transpiler tests: visitor method → expression/statement handling → code emission
- For type resolution tests: type resolver → type mapping → output type string
