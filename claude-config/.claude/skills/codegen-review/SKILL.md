---
description: Review generated code against Datrix quality standards and submission checklist
model: sonnet
disable-model-invocation: true
---

# Codegen Review

## Run the Scanners FIRST (scripted checklist)

Most checklist items below have a deterministic scanner — run the scanners on the touched package(s) and reason only about what they flag, instead of eyeballing code against the criteria. Read `datrix/scripts/quick-reference.md` (and the relevant category file) before invoking any script — a pre-tool hook enforces this. Invoke from bash as `powershell -File "d:/datrix/datrix/scripts/<category>/<script>.ps1" {package}`.

| Checklist item | Scanner |
|---|---|
| No placeholders/TODOs, no debug scatter | `dev\check-debug-artifacts.ps1 {package}`; `dev\ast-grep.ps1 {package}` |
| No silent fallbacks | `dev\libcst.ps1 {package}`; `dev\semgrep.ps1 {package}` |
| No `except: pass` | covered by `dev\semgrep.ps1` / `dev\ast-grep.ps1` rules |
| All tests pass | `test\test.ps1 {package}` |
| No cross-package / matrix tests | `dev\check-import-boundaries.ps1` |
| Cognitive complexity ≤15 | `metrics\complexity.ps1 {package}` |
| No redundant code | `metrics\duplicate.ps1 {package}`; dead code: `metrics\vulture.ps1 {package}` |
| No magic constants | `dev\find-constants.ps1 {package} -Output D:\datrix\.test-output\strings.md` (report defaults to CWD — always redirect) |
| No `Any` type annotations | `test\mypy.ps1 {package}` + Grep for `: Any` |
| Lint clean | `metrics\ruff.ps1 {package}` |

Manual judgment remains for: mocks/fakes in tests, test-guideline conformance, docstrings, key=value logging format, logic-map markers, and generated-code validity.

## Submission Checklist

- [ ] No placeholders/TODOs
- [ ] No mocks/fakes
- [ ] No silent fallbacks
- [ ] All tests pass (pytest)
- [ ] Tests follow test guidelines (real objects, output validation, error cases)
- [ ] No cross-package or language/provider matrix tests — each `datrix-*` package tests only its own surface; no `datrix/tests/` suite (Datrix is multi-language, multi-platform)
- [ ] Generated code valid (if applicable)
- [ ] Docstrings on public APIs
- [ ] Standard logging with key=value format
- [ ] Cognitive complexity ≤15 per function
- [ ] No redundant code
- [ ] No magic constants
- [ ] No `Any` type annotations
- [ ] Logic map markers added/updated if applicable
- [ ] Queried logic map database before writing significant new logic

## Repository Rules

### datrix-common
- ZERO runtime deps on other Datrix packages (datrix-language is dev/test only)
- Only stdlib + external packages at runtime
- YAML/JSON builders for data format generation

### datrix-language
- Parser + CST-to-AST transformers only (thin package)
- Immutable CST nodes (frozen dataclasses)
- All lookups raise on not found

### datrix-codegen-* (component, python, typescript, sql)
- Jinja2 templates + ruff format (Python) / Prettier (TypeScript)
- Exhaustive type mappings. Validate generated code.

### datrix-codegen-* (docker, aws, azure)
- YAML/JSON builders. Validate manifests.

## Anti-Patterns

- **NO workarounds** — don't steer around issues, don't paper over them. **Fix the root cause, wherever it lives** (CLAUDE.md rule). This is not a binary between "workaround" and "stop": the third option — do the real work — is the default. Stopping is licensed only by a proven B1–B4 blocker with the four-part proof (`.claude/skills/_shared/execution-contract.md`).
- **NO dodging** — "out of scope", "pre-existing", "categorically behavioral", "should be tracked separately", "not my package" are **not** blockers; they are the work. A `SubagentStop` hook greps reports for this vocabulary.
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
