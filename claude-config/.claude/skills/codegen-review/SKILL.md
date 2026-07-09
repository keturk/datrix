---
description: Review generated code against Datrix quality standards and submission checklist
model: sonnet
disable-model-invocation: true
---

# Codegen Review

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

- **NO workarounds** — don't steer around issues, don't paper over them; fix the root cause or STOP and report (CLAUDE.md rule)
- **NO git restore/checkout/reset/stash/revert** — undo edits manually (CLAUDE.md rule)
