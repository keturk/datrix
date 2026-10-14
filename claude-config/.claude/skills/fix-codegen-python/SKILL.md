---
description: Diagnose and fix datrix-codegen-python test failures, errors, and warnings from structured test results
model: claude-sonnet-5-5
effort: high
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

- **Table rows:** a failing `tests/test_tables.py::test_table[<table>::<row>]` item is a row defect or a code-path defect: fix the row (the registry, type-map or emit row, the DAL generator declaration) or the code that realizes it — never add a test or an exclusion. A builtin the target neither realizes nor declares a `builtin_group:<group>` capability gap for is a product defect to fix or a gap row to declare. `datrix/scripts/test/tables.ps1 rows <package>` lists the items.
- **Scope:** Python codegen ONLY. Do NOT cross into TypeScript codegen packages.
- **Model contracts:** a failing `tests/test_model_contracts.py::test_model_contract[<Model>::<field>::<fact>]` item, or a model `test_every_model_has_a_fixture_sample` names, is a model or fixture defect: fix the model's declaration or the `.dcfg` fixture (add one whose load reaches the model) — never the runner, never with a new test. `datrix/scripts/test/model-contracts.ps1 facts <package> [<Model>]` shows each model's items and the fixture its sample came from.
- **Package:** `datrix-codegen-python` — Python codegen.
- **Fix target:** Generator source code, templates, transpiler, or test code — never generated output. A failing declarative case (`tests/test_cases.py::test_case[<area>::<case-id>]`: a row, or an annotation such as `// @emits <expression>` on a fixture line) is fixed in product code, or by a person correcting the authored expectation or annotation in review — never by writing a code test for the same fact (`guard-code-standards.py` refuses one).

### Additional Test-to-Source Mapping

| Test file path | Source file path |
|---|---|
| `tests/unit/transpiler/test_operators.py` | `src/.../transpiler/operators.py` |
| `tests/transpiler/test_py_statements_coverage.py` | `src/.../transpiler/_transpiler_statements.py` + `_transpiler_expressions.py` |

### Trace Failures to Source (generator/transpiler specifics)

- For generator tests: generator function → template context → template rendering
- For transpiler tests: visitor method → expression/statement handling → code emission
- For type resolution tests: type resolver → type mapping → output type string
