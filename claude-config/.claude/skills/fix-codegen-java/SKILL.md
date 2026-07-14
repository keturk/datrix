---
description: Diagnose and fix datrix-codegen-java test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Codegen Java

Diagnose and fix failures, errors, and warnings in `datrix-codegen-java` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-java D:\datrix\datrix-codegen-java\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-java`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-java\`

## Package Specifics

- **Scope:** Java codegen ONLY. Do NOT cross into sibling language codegen packages (`datrix-codegen-python`, `-typescript`, `-dotnet`) — they are import-forbidden siblings, not a place to fix or compare against.
- **Package:** `datrix-codegen-java` — Java codegen.
- **Fix target:** Generator source code, templates, transpiler, or test code — never generated output.

### Trace Failures to Source (generator/transpiler specifics)

- For generator tests: generator function → template context → template rendering
- For transpiler tests: visitor method → expression/statement handling → code emission
- For type resolution tests: type resolver → type mapping → output type string

### Shared-layer boundary

A defect that turns out to live in `datrix-codegen-common` (the shared transpiler, `LanguageProfile` / `SyntaxEmitters`, context builders, genDSL) or in `datrix-common` is fixed **there**, not worked around here — but that layer is consumed by EVERY language generator, so a change to it must keep every other consuming package's suite green (CLAUDE.md's cross-surface impact rule). Cross-language parity is verified by per-language conformance against the declared contracts in `datrix-codegen-common`, never by importing or comparing against a sibling language package.
