---
description: Diagnose and fix datrix-codegen-angular test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Codegen Angular

Diagnose and fix failures, errors, and warnings in `datrix-codegen-angular` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-angular D:\datrix\datrix-codegen-angular\.test_results\test-results-YYYYMMDD-HHMMSS\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-angular`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-angular\`

## Package Specifics

- **Scope:** Angular frontend-client codegen ONLY. Do NOT cross into the backend language codegen packages (`datrix-codegen-typescript`, `-python`, `-java`, `-dotnet`).
- **Package:** `datrix-codegen-angular` — frontend API client generation (models, enums, injectable HTTP clients, route/provider manifest).
- **Fix target:** Generator source code, GenDSL definitions, Jinja2 templates, or test code — never generated output.

### This is a frontend TARGET, not a language

- Registered as an artifact-phase **`datrix.generators`** plugin (`angular = datrix_codegen_angular.plugin:AngularClientGenerator`), **not** a `datrix.languages` plugin. It never appears in `registered_language_names()`, and `--language` never selects it — `--language` selects the *backend*.
- Activation is a declared config fact: `active_for_angular_client()` returns true only when the application declares a `clients { angular { … } }` block. A test asserting "nothing was emitted" for an app without that block is asserting activation, not a bug.
- It emits **TypeScript** (`_ANGULAR_OUTPUT_LANGUAGE = "typescript"` in `plugin.py`), declares its own file language and type map, and **must never import `datrix_codegen_typescript`**. `tests/unit/test_import_isolation.py` is a static AST scan proving that; `tests/integration/test_generation_without_typescript.py` (with `no_typescript_generation_probe.py`) proves it at generation time. Never "fix" a failure by importing the backend TypeScript package.
- The run's resolved **backend** language is load-bearing in exactly one place: query-parameter wire-name casing and the offset-pagination parameter pair, both read from the backend's `LanguageCapabilityDeclaration` via `build_client_contract`. Never hardcode `skip`/`limit` or a casing rule.

### Key Entry Points

| File | Purpose |
|---|---|
| `plugin.py` | `AngularClientGenerator` — compiles the GenDSL definitions, builds the client contract, renders, checks type-map completeness |
| `activation.py` | `active_for_angular_client()`, `ANGULAR_CLIENT_TARGET_KEY` — the `clients { angular { … } }` gate |
| `client_settings.py` | `parse_angular_client_settings()` — `baseUrlToken`; unknown settings are rejected, not ignored |
| `gendsl_definitions.py` | `angular_client_definition()` — the whole emission spec (`domain models` / `endpoints` / `manifest`) and every output path |
| `gendsl/registrations.py` | `register_file_languages` / `register_context_namespaces` / `register_generator_target` (kind `"component"`) |
| `gendsl/api.py` | `build_api_context`, `has_browser_routes`, path/query/body param contexts |
| `gendsl/models.py` | `build_struct_context` / `build_entity_context` / `build_enum_context` + the three mutually exclusive closure predicates |
| `gendsl/manifest.py` | `build_manifest_context`, `build_file_manifest`, `verify_file_manifest`, `build_readme` |
| `type_mappings.py` | `ANGULAR_TYPE_MAP`, extension maps, `apply_json_wire_overrides`, `UnmappedBuiltinTypeError` |
| `type_resolution.py` | `resolve_route_type`, `resolve_closure_type_ref`, `check_type_map_completeness` |
| `ts_local_names.py` | `allocate_local_names` — import aliasing and collision-free local names |
| `ts_source.py` | Escapers/validators for emitted TypeScript (`escape_ts_string`, `require_ts_binding_identifier`, …) + `register_ts_source_filters` |
| `templates/` | `models/struct.ts.j2`, `models/enum.ts.j2`, `endpoints/client.ts.j2`, `core/*.ts.j2`, `manifest/*.ts.j2` |

### Emission Layout (from `gendsl_definitions.py`)

```
domain models    → libs/api-contract/src/lib/models/{container}/…  + core/branded.ts
domain endpoints → libs/api-client/src/lib/{api}.client.ts
                   + libs/api-client/src/lib/core/api-base-url.token.ts
                   + libs/api-client/src/lib/core/query-params.ts
domain manifest  → libs/api-contract/src/lib/routes/route-manifest.ts + providers.ts
```

Iteration is over the contract's **computed type closure** (`each client_type`) and **`each client_api`** — never `each service { each struct }` and never separate `rest_api`/`serverless_block` clauses. A failure about a missing or extra emitted file is usually a closure/predicate question, not a template question.

### Test-to-Source Mapping

| Test file path | Source file path |
|---|---|
| `tests/unit/test_plugin.py` | `src/.../plugin.py` |
| `tests/unit/test_activation.py` | `src/.../activation.py` |
| `tests/unit/test_client_settings.py` | `src/.../client_settings.py` |
| `tests/unit/test_gendsl_angular_defs.py`, `tests/unit/test_client_file_bindings.py` | `src/.../gendsl_definitions.py` (+ `templates/`) |
| `tests/unit/gendsl/test_api_context.py` | `src/.../gendsl/api.py` |
| `tests/unit/gendsl/test_models_context_builders.py` | `src/.../gendsl/models.py` |
| `tests/unit/gendsl/test_manifest.py` | `src/.../gendsl/manifest.py` |
| `tests/unit/gendsl/test_registrations.py` | `src/.../gendsl/registrations.py` |
| `tests/unit/test_type_mappings.py`, `tests/unit/test_type_map_completeness.py` | `src/.../type_mappings.py`, `type_resolution.py::check_type_map_completeness` |
| `tests/unit/test_type_resolution.py` | `src/.../type_resolution.py` |
| `tests/unit/test_ts_local_names.py` | `src/.../ts_local_names.py` |
| `tests/unit/test_ts_string_escaping.py` | `src/.../ts_source.py` |
| `tests/integration/test_endpoint_emission.py` | `templates/endpoints/client.ts.j2` + `gendsl/api.py` |
| `tests/integration/test_models_domain_emission.py` | `templates/models/*.ts.j2` + `gendsl/models.py` |
| `tests/integration/test_manifest_emission.py` | `templates/manifest/*.ts.j2` + `gendsl/manifest.py` |
| `tests/integration/test_hostile_text_emission.py` | `src/.../ts_source.py` escapers |
| `tests/integration/test_identifier_collision_emission.py` | `src/.../ts_local_names.py` |
| `tests/integration/test_generation_without_typescript.py` | `tests/integration/no_typescript_generation_probe.py` (subprocess probe) |
| `tests/unit/test_import_isolation.py` | static AST scan over `src/datrix_codegen_angular/` |
| `tests/unit/test_npm_tsc_pooling.py` | `tests/conftest.py` (`pytest_collection_modifyitems`) |

### Test Fixtures and Helpers

- `tests/conftest_shared.py` — `make_angular_context(backend_language, profile="test")` builds a `CodegenContext`. Vary `backend_language` to prove a rule is derived from the backend declaration rather than hardcoded.
- `tests/conftest.py` — `.dtrx`-backed application fixtures parsed through the real parser and semantic analyzer: `minimal_angular_app`, `app_with_angular_client`, `app_with_reachable_struct_and_enum`, `app_with_client_endpoints`, `app_with_unreachable_struct`. Fixture `.dtrx` sources live in `tests/fixtures/`.
- Real objects only — no mocks, no `SimpleNamespace`.

### `npm_tsc` tests run a real toolchain

Tests marked `npm_tsc` (e.g. `tests/integration/test_models_domain_tsc.py`) run a real `npm install` plus `tsc`/`tsx` on the emitted client. `tests/conftest.py` spreads them over `DATRIX_TS_NPM_TSC_POOLS` (default 4) xdist `loadgroup` pools to bound concurrency.

- A **compile diagnostic** from `tsc` is a real defect in the emitted TypeScript — read the diagnostic and fix the template, context builder, or type map.
- A **subprocess timeout** with no diagnostic is a contention/pooling symptom: confirm it by re-running that one test alone with `test-single.ps1` before touching generator code. Never widen a timeout or drop the marker to make it green.

### Invariants a Fix Must Not Break

These are gated by this package's own tests; a change that turns a test green by violating one of them is a defect, not a fix (`datrix/docs/architecture/architecture-overview.md` — Decision 43):

- **No secret, token, credential, tenant id, environment URL, or per-profile value in any emitted file.** The base URL is *injected* through a declared token, never emitted. Pagination parameters are emitted optional with no default, no bound, and no value-bearing comment.
- **A machine-only surface is never emitted into a browser client.** Classification branches on `AuthMode` with a fail-loud default — never on provider-tuple emptiness (public, webhook, and undeclared routes all carry an empty tuple).
- **Every emitted type is mapped and every referenced type is emitted.** No default mapping, no `any`, no silent `string`; an unmapped type raises `UnmappedBuiltinTypeError` / fails `check_type_map_completeness` naming the type.
- **A caller value never reaches a URL by concatenation** — path parameters are percent-encoded at the call site.
- **Request-body encoding is decided, never assumed** — a file-upload field binds multipart; an undecidable encoding raises.
- **Author-supplied text cannot break out of emitted source** — every literal goes through the `ts_source.py` escaper/validator for its position.
- **The provider manifest is metadata, not an authorization control.** The server stays the only enforcement point; never narrow a client per consuming application.

### Shared-layer boundary

The framework-neutral **client contract** — routes, params (DSL name *and* wire name), response type refs, provider sets, body encoding, pagination flags — lives in `datrix-codegen-common` (`generation/client_contract.py`), and the GenDSL compiler/executor and parity declarations live there too. A defect in any of those is fixed **there**, not worked around here — but that layer is consumed by EVERY generator, so a change to it must keep the changed behaviour's tagged tests green in every consuming package it reaches (CLAUDE.md's cross-surface impact rule). A per-frontend-target difference is a declared parameter or a renderer-local rendering step, never a target-name conditional in the shared layer — no frontend-target name may appear in a shared type, field, or alias.
