---
description: Diagnose and fix datrix-codegen-sql test failures, errors, and warnings from structured test results
model: claude-sonnet-5-5
effort: high
---

# Fix Codegen SQL

Diagnose and fix failures, errors, and warnings in `datrix-codegen-sql` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-sql D:\datrix\datrix-codegen-sql\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-sql`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-sql\`

## Package Specifics

- **Table rows:** a failing `tests/test_tables.py::test_table[<table>::<row>]` item is a row defect or a code-path defect: fix the row (the registry, type-map or emit row, the DAL generator declaration) or the code that realizes it — never add a test or an exclusion. A builtin the target neither realizes nor declares a `builtin_group:<group>` capability gap for is a product defect to fix or a gap row to declare. `datrix/scripts/test/tables.ps1 rows <package>` lists the items.
- **Scope:** `datrix-codegen-sql` — SQL codegen.
- **Fix target:** Generator source code, templates, or test code — never generated output. A failing declarative case (`tests/test_cases.py::test_case[<area>::<case-id>]`) is fixed in product code, or by a person correcting the authored expectation in review — never by writing a code test for the same fact (`guard-code-standards.py` refuses one).
