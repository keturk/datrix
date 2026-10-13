---
description: Diagnose and fix datrix-codegen-kernel test failures, errors, and warnings from structured test results
model: claude-opus-5-5
effort: high
---

# Fix Codegen Kernel

Diagnose and fix failures, errors, and warnings in `datrix-codegen-kernel` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-kernel D:\datrix\datrix-codegen-kernel\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-kernel`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-kernel\`

## Package Specifics

- **Scope:** `datrix-codegen-kernel` — the target-neutral generation framework: generator base classes, template engine, discovery, type-mapping registry, shared route and runtime derivations, deploy-script machinery, DAL generator data model, Seed datasets, SQL dialect facts.
- **Fix target:** Source code or test code — never generated output. A failing declarative case (`tests/test_cases.py::test_case[<area>::<case-id>]`) is fixed in product code, or by a person correcting the authored expectation in review — never by writing a code test for the same fact (`guard-code-standards.py` refuses one).
- **Model contracts:** a failing `tests/test_model_contracts.py::test_model_contract[<Model>::<field>::<fact>]` item, or a model `test_every_model_has_a_fixture_sample` names, is a model or fixture defect: fix the model's declaration or the `.dcfg` fixture (add one whose load reaches the model) — never the runner, never with a new test. `datrix/scripts/test/model-contracts.ps1 facts <package> [<Model>]` shows each model's items and the fixture its sample came from.
- **Boundary:** depends on `datrix-common` only and loads no language-layer, generator, parser, semantic, or CLI module (import-linter contract + fresh-subprocess test). A fix must never add an import of `datrix_codegen_common`, a generator package, or `datrix_semantic` — if the fix seems to need one, the logic belongs in the other package.
- **Target-neutral:** no language or platform name in kernel code. Per-target behaviour is declared by the plugin and read here, never branched on here.
- **CAUTION:** Every generator, `datrix-codegen-common`, `datrix-cli`, and `datrix-testing` consume this package (per CLAUDE.md's cross-surface impact rule). Flag any public-contract change and run the changed behaviour's feature tags in every consuming package it reaches (never a whole suite).
