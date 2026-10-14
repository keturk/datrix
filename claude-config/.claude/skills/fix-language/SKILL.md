---
description: Diagnose and fix datrix-language test failures, errors, and warnings from structured test results
model: claude-opus-5-5
effort: high
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

- **Table rows:** a failing `tests/test_tables.py::test_table[<table>::<row>]` item is a row defect or a code-path defect: fix the row (a builtin declaration of `builtins.dtrx`) or the code that realizes it — never add a test or an exclusion. `datrix/scripts/test/tables.ps1 rows datrix-language` lists the items.
- **Scope:** `datrix-language` — DSL parser and language package.
- **Fix target:** Parser, transformer, validator, or test code. A failing declarative case (`tests/test_cases.py::test_case[<area>::<case-id>]`: a row, an annotation on a fixture line such as `// @hover …` at a `$0` cursor, or a docs fence) is fixed in product code, or by a person correcting the authored expectation, annotation or fence in review — never by writing a code test for the same fact (`guard-code-standards.py` refuses one).
- **CAUTION:** Changes to datrix-language affect ALL downstream packages that parse .dtrx files. Be especially careful with grammar and AST changes.
