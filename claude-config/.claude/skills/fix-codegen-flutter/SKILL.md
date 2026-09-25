---
description: Diagnose and fix datrix-codegen-flutter test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Codegen Flutter

Diagnose and fix failures, errors, and warnings in `datrix-codegen-flutter` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-flutter D:\datrix\datrix-codegen-flutter\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-flutter`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-flutter\`

## Package Specifics

- **Scope:** Flutter mobile-target codegen ONLY. Do NOT cross into the backend language codegen packages (`datrix-codegen-typescript`, `-python`, `-java`, `-dotnet`) or into the sibling frontend targets `datrix-codegen-angular` and `datrix-codegen-react`.
- **Package:** `datrix-codegen-flutter` — Flutter (Dart) mobile-application generation from the shared client contract and UI contract (typed API clients, route manifests, and generated pages, forms, tables, layouts and the AppAuth-based login/session layer).
- **Fix target:** Generator source code, GenDSL definitions, Jinja2 templates, or test code — never generated output.
- **Module layout and test-to-source mapping:** read `d:\datrix\datrix-codegen-flutter\docs\architecture.md` — the package's own architecture doc is the one home for its file inventory, and this skill does not restate it. A test file with no counterpart named there is a doc defect to fix in the same change.

### This is a frontend TARGET, not a language

- Registered as an artifact-phase **`datrix.generators`** plugin (`flutter = datrix_codegen_flutter.plugin:FlutterClientGenerator`), **not** a `datrix.languages` plugin. It never appears in `registered_language_names()`, and `--language` never selects it — `--language` selects the *backend*.
- Activation is a declared config fact: `active_for_flutter_client()` returns true only when the application declares a `clients { flutter { … } }` block. A test asserting "nothing was emitted" for an app without that block is asserting activation, not a bug.
- It emits **Dart** and declares its own `"dart"` file language, type map, and escaper/validator for emitted Dart source. No other package declares Dart, so its declaration is load-bearing, never a no-op. It **must never import a backend language package or another frontend target**; its import-isolation test is a static AST scan proving that.
- It owns a full **Dart transpiler core** (`transpiler/core.py` `DartTranspilerCore(LanguageTranspiler)`, visitors, operators, `DartBuiltinMethodMapper`, emit tables, `syntax_emitters.py`) and the `LanguageProfile` that drives the shared transpiler — the dotnet/java package shape. `parity_checker.py` runs over the profile in this package's own suite; a red result there is a missing operator, scalar annotation or builtin row in this package, fixed here. `builtin_group_stances` is complete over every `BuiltinGroup`; a `supported` group with an unmapped row fails at package load and is fixed by adding the row or declaring `unsupported(reason)` — never by loosening the check.
- Its output is re-rooted under `clients/flutter/` by the shared layer (`datrix_common.generation.client_output`); a failure about a path outside that subtree is a shared-layer question, never a template question.
- The run's resolved **backend** language is load-bearing in exactly one place: query-parameter wire-name casing and the offset-pagination parameter pair, both read from the backend's `LanguageCapabilityDeclaration` via `build_client_contract`. Never hardcode `skip`/`limit` or a casing rule.

### Tests that run the Flutter toolchain

Tests marked for the Flutter toolchain run a real `flutter pub get` plus `flutter analyze` (and `dart format --set-exit-if-changed`) on the emitted app. They skip — never silently pass — when the Flutter SDK is not on `PATH`, and they are pooled the way `datrix-codegen-typescript`'s and `datrix-codegen-angular`'s `npm_tsc` tests are, to bound concurrency.

- An **analyzer diagnostic** is a real defect in the emitted Dart — read it and fix the template, context builder, or type map.
- A **subprocess timeout** with no diagnostic is a contention/pooling symptom: confirm it by re-running that one test alone with `test-single.ps1` before touching generator code. Never widen a timeout or drop the marker to make it green.

### Invariants a Fix Must Not Break

These are gated by this package's own tests; a change that turns a test green by violating one of them is a defect, not a fix (`datrix/docs/architecture/architecture-overview.md` — Decision 43 and the UI-language decision that extends it):

- **No secret, token, credential, tenant id, environment URL, or per-profile value in any emitted file.** Per-environment values reach the running app only through the bundled runtime-config asset loaded at startup; the emitted tree is byte-identical across profiles.
- **A machine-only surface is never emitted into a client.** Classification branches on `AuthMode` with a fail-loud default — never on provider-tuple emptiness.
- **Every emitted type is mapped and every referenced type is emitted.** No default mapping, no `dynamic`, no silent `String`; an unmapped type fails the completeness check naming the type.
- **A caller value never reaches a URL by concatenation** — path parameters and `Nav.to` arguments are percent-encoded into their segment at the call site; the path itself is always the target page's declared `@path` literal.
- **Request-body encoding is decided, never assumed** — a file-upload field binds multipart; an undecidable encoding raises.
- **Author-supplied text cannot break out of emitted source** — every literal goes through the package's Dart escaper/validator for its position.
- **Sensitive and hidden fields are never derived into a form or table**, and login is Authorization Code + PKCE through the system browser via AppAuth with an app-scheme redirect, tokens held in the platform keychain/keystore — never `implicit`, never a credential form, never plain shared preferences or a file.
- **Route guards and the provider manifest are metadata, not an authorization control.** The server stays the only enforcement point; never narrow a client per consuming application.
- **A Datrix body behaves the same here as on every other target.** `fn` bodies, `state` initializers, bindings and view expressions are transpiled by the shared transpiler under this package's Dart profile; the rendered-output tests over the shared behaviour fixture and the behaviour-parity gate hold this package to the one correct behaviour — there is no reference language; a divergence is reconciled to the best copy (fails closed, reads everything the DSL declares, most secure, most correct output). A failure in a transpiled body is fixed in the profile (a builtin row, an emit-table row, a syntax emitter) or, when the shared behaviour itself is wrong, in the shared core — never by special-casing a construct in a template.

### Shared-layer boundary

The framework-neutral **client contract** (`generation/client_contract.py`), **UI contract** (`generation/ui_contract.py`), client transpile-context builder (`generation/client_transpile_context.py`) and the fail-closed client entity-query module (`transpiler/client_entity_query.py`) live in `datrix-codegen-common`, and the GenDSL compiler/executor, the builtin registry and the parity declarations live there too. A defect in any of those is fixed **there**, not worked around here — but that layer is consumed by EVERY generator, so a change to it must keep the changed behaviour's tagged tests green in every consuming package it reaches (CLAUDE.md's cross-surface impact rule). A per-frontend-target difference is a declared parameter or a renderer-local rendering step, never a target-name conditional in the shared layer — no frontend-target name may appear in a shared type, field, or alias, and nothing mobile-shaped (a "mobile" flag, a platform branch) may appear there either: a target is mobile because this package says so and emits what a mobile framework needs. The multi-renderer agreement gate (identical route-key and screen-key manifests across every activated client target) is the check that catches a shared-layer change leaking a Flutter or web shape.
