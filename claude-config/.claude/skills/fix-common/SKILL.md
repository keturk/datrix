---
description: Diagnose and fix datrix-common test failures, errors, and warnings from structured test results
model: claude-opus-5-5
effort: high
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

- **Scope:** shared framework library — fix source code or test code. A failing declarative case (`tests/test_cases.py::test_case[<area>::<case-id>]`) is fixed in product code, or by a person correcting the authored expectation in review — never by writing a code test for the same fact (`guard-code-standards.py` refuses one).
- **Model contracts:** a failing `tests/test_model_contracts.py::test_model_contract[<Model>::<field>::<fact>]` item, or a model `test_every_model_has_a_fixture_sample` names, is a model or fixture defect: fix the model's declaration or the `.dcfg` fixture (add one whose load reaches the model) — never the runner, never with a new test. `datrix/scripts/test/model-contracts.ps1 facts <package> [<Model>]` shows each model's items and the fixture its sample came from.
- **CAUTION:** Changes to datrix-common can affect ALL downstream packages (every generator consumes it). Be especially careful with API changes; per CLAUDE.md's cross-surface impact rule, flag any public-contract change and run the changed behaviour's feature tags in every consuming package it reaches (never a whole suite).
