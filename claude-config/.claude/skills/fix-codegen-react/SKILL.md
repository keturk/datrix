---
description: Diagnose and fix datrix-codegen-react test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Codegen React

Diagnose and fix failures, errors, and warnings in `datrix-codegen-react` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-react D:\datrix\datrix-codegen-react\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-react`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-react\`

## Package Specifics

- **Scope:** React frontend-target codegen ONLY. Do NOT cross into the backend language codegen packages (`datrix-codegen-typescript`, `-python`, `-java`, `-dotnet`) or into the sibling frontend target `datrix-codegen-angular`.
- **Package:** `datrix-codegen-react` — React frontend generation from the shared client contract and UI contract (typed API client modules, route/provider manifests, and generated pages, forms, tables, layouts and the hosted-login session layer).
- **Fix target:** Generator source code, GenDSL definitions, Jinja2 templates, or test code — never generated output.
- **Module layout and test-to-source mapping:** read `d:\datrix\datrix-codegen-react\docs\architecture.md` — the package's own architecture doc is the one home for its file inventory, and this skill does not restate it. A test file with no counterpart named there is a doc defect to fix in the same change.

### This is a frontend TARGET, not a language

- Registered as an artifact-phase **`datrix.generators`** plugin (`react = datrix_codegen_react.plugin:ReactClientGenerator`), **not** a `datrix.languages` plugin. It never appears in `registered_language_names()`, and `--language` never selects it — `--language` selects the *backend*.
- Activation is a declared config fact: `active_for_react_client()` returns true only when the application declares a `clients { react { … } }` block. A test asserting "nothing was emitted" for an app without that block is asserting activation, not a bug.
- It emits **TypeScript**, declares its own file language and type map, and **never imports `datrix_codegen_angular`**. From `datrix_codegen_typescript` it imports exactly the TypeScript transpiler core and language sub-profiles (`transpiler`, `transpiler.operators`, `syntax_emitters`, `type_mappings`) — the one home of the TypeScript emitter — and nothing else: no generator, template, GenDSL or language-hook module. Its import-isolation test is a static AST scan with exactly that allowlist. Never "fix" a failure by importing a backend generator module or the Angular target, and never "fix" one by copying a transpiler visitor into this package — a second TypeScript emitter is the defect the allowlist exists to prevent.
- Its `TranspilerProfile` composes the shared core with a React `BuiltinProfile` (browser rows for every group it declares `supported`) and the fail-closed client entity-query module from `datrix-codegen-common`. `builtin_group_stances` is complete over every `BuiltinGroup`; a `supported` group with an unmapped row fails at package load, and that failure is fixed by adding the row or declaring the group `unsupported(reason)` — never by loosening the check.
- Its output is re-rooted under `clients/react/` by the shared layer (`datrix_common.generation.client_output`); a failure about a path outside that subtree is a shared-layer question, never a template question.
- The run's resolved **backend** language is load-bearing in exactly one place: query-parameter wire-name casing and the offset-pagination parameter pair, both read from the backend's `LanguageCapabilityDeclaration` via `build_client_contract`. Never hardcode `skip`/`limit` or a casing rule.

### `npm_tsc` tests run a real toolchain

Tests marked `npm_tsc` run a real `npm install` plus `tsc --noEmit` on the emitted workspace. They are pooled over `DATRIX_TS_NPM_TSC_POOLS` (default 4) xdist `loadgroup` pools to bound concurrency, exactly as `datrix-codegen-typescript` and `datrix-codegen-angular` do.

- A **compile diagnostic** from `tsc` is a real defect in the emitted TypeScript — read the diagnostic and fix the template, context builder, or type map.
- A **subprocess timeout** with no diagnostic is a contention/pooling symptom: confirm it by re-running that one test alone with `test-single.ps1` before touching generator code. Never widen a timeout or drop the marker to make it green.

### Invariants a Fix Must Not Break

These are gated by this package's own tests; a change that turns a test green by violating one of them is a defect, not a fix (`datrix/docs/architecture/architecture-overview.md` — Decision 43 and the UI-language decision that extends it):

- **No secret, token, credential, tenant id, environment URL, or per-profile value in any emitted file.** Per-environment values reach the running app only through the runtime-config asset loaded at bootstrap; the emitted tree is byte-identical across profiles.
- **A machine-only surface is never emitted into a browser client.** Classification branches on `AuthMode` with a fail-loud default — never on provider-tuple emptiness.
- **Every emitted type is mapped and every referenced type is emitted.** No default mapping, no `any`, no silent `string`; an unmapped type fails the completeness check naming the type.
- **A caller value never reaches a URL by concatenation** — path parameters and `Nav.to` arguments are percent-encoded into their segment at the call site; the path itself is always the target page's declared `@path` literal.
- **Request-body encoding is decided, never assumed** — a file-upload field binds multipart; an undecidable encoding raises.
- **Author-supplied text cannot break out of emitted source** — every literal goes through the package's escaper/validator for its position; view text renders as text nodes, never as raw HTML.
- **Sensitive and hidden fields are never derived into a form or table**, and login is hosted Authorization Code + PKCE with tokens held in memory — never `implicit`, never a credential form, never `localStorage`.
- **Route guards and the provider manifest are metadata, not an authorization control.** The server stays the only enforcement point; never narrow a client per consuming application.
- **A Datrix body behaves the same here as on every other target.** `fn` bodies, `state` initializers, bindings and view expressions are transpiled by the shared transpiler under this package's profile; the rendered-output tests over the shared behaviour fixture and the behaviour-parity gate hold this package to the one correct behaviour — there is no reference language; a divergence is reconciled to the best copy (fails closed, reads everything the DSL declares, most secure, most correct output). A failure in a transpiled body is fixed in the profile (a builtin row, an emit-table row, a syntax emitter) or, when the shared behaviour itself is wrong, in the shared core — never by special-casing a construct in a template.

### Shared-layer boundary

The framework-neutral **client contract** (`generation/client_contract.py`), **UI contract** (`generation/ui_contract.py`), client transpile-context builder (`generation/client_transpile_context.py`) and the fail-closed client entity-query module (`transpiler/client_entity_query.py`) live in `datrix-codegen-common`, and the GenDSL compiler/executor, the builtin registry and the parity declarations live there too. A defect in any of those is fixed **there**, not worked around here — but that layer is consumed by EVERY generator, so a change to it must keep the changed behaviour's tagged tests green in every consuming package it reaches (CLAUDE.md's cross-surface impact rule). A per-frontend-target difference is a declared parameter or a renderer-local rendering step, never a target-name conditional in the shared layer — no frontend-target name may appear in a shared type, field, or alias. The two-renderer agreement gate (identical route-key and screen-key manifests across every activated client target) is the check that catches a shared-layer change leaking a React shape.
