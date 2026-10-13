---
description: Diagnose and fix datrix-cli test failures, errors, and warnings from structured test results
model: claude-sonnet-5-5
effort: high
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
- **Fix target:** Source code or test code — never generated output. A failing declarative case (`tests/test_cases.py::test_case[<area>::<case-id>]`) is fixed in product code, or by a person correcting the authored expectation in review — never by writing a code test for the same fact (`guard-code-standards.py` refuses one).
- **Model contracts:** a failing `tests/test_model_contracts.py::test_model_contract[<Model>::<field>::<fact>]` item, or a model `test_every_model_has_a_fixture_sample` names, is a model or fixture defect: fix the model's declaration or the `.dcfg` fixture (add one whose load reaches the model) — never the runner, never with a new test. `datrix/scripts/test/model-contracts.ps1 facts <package> [<Model>]` shows each model's items and the fixture its sample came from.
