---
description: Diagnose and fix datrix-codegen-angular test failures, errors, and warnings from structured test results
model: claude-sonnet-5-5
effort: high
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

- **Table rows:** a failing `tests/test_tables.py::test_table[<table>::<row>]` item is a row defect or a code-path defect: fix the row (the registry, type-map or emit row, the DAL generator declaration) or the code that realizes it — never add a test or an exclusion. A builtin the target neither realizes nor declares a `builtin_group:<group>` capability gap for is a product defect to fix or a gap row to declare. `datrix/scripts/test/tables.ps1 rows <package>` lists the items.
- **Scope:** Angular frontend-client codegen ONLY. Do NOT cross into the backend language codegen packages (`datrix-codegen-typescript`, `-python`, or any other registered language) or into the sibling frontend target `datrix-codegen-flutter`.
- **Package:** `datrix-codegen-angular` — frontend API client generation (models, enums, injectable HTTP clients, route/provider manifest).
- **Fix target:** Generator source code, DAL generator definitions, Jinja2 templates, or test code — never generated output. A failing declarative case (`tests/test_cases.py::test_case[<area>::<case-id>]`) is fixed in product code, or by a person correcting the authored expectation in review — never by writing a code test for the same fact (`guard-code-standards.py` refuses one).

### This is a frontend TARGET, not a language

- Registered as an artifact-phase **`datrix.generators`** plugin (`angular = datrix_codegen_angular.plugin:AngularClientGenerator`), **not** a `datrix.languages` plugin. It never appears in `registered_language_names()`, and `--language` never selects it — `--language` selects the *backend*.
- Activation is a declared config fact: `active_for_angular_client()` returns true only when the application declares a `clients { angular { … } }` block. A test asserting "nothing was emitted" for an app without that block is asserting activation, not a bug.
- It emits **TypeScript** (`_ANGULAR_OUTPUT_LANGUAGE = "typescript"` in `plugin.py`), declares its own file language and type map, and **must never import `datrix_codegen_typescript`**. `tests/unit/test_import_isolation.py` is a static AST scan proving that; `tests/integration/test_generation_without_typescript.py` (with `no_typescript_generation_probe.py`) proves it at generation time. Never "fix" a failure by importing the backend TypeScript package.
- The run's resolved **backend** language is load-bearing in exactly one place: query-parameter wire-name casing and the offset-pagination parameter pair, both read from the backend's `LanguageCapabilityDeclaration` via `build_client_contract`. Never hardcode `skip`/`limit` or a casing rule.

### Key Entry Points

| File | Purpose |
|---|---|
| `plugin.py` | `AngularClientGenerator` — compiles the DAL generator definitions, builds the client contract, renders, checks type-map completeness |
| `activation.py` | `active_for_angular_client()`, `ANGULAR_CLIENT_TARGET_KEY` — the `clients { angular { … } }` gate |
| `client_settings.py` | `parse_library_only_settings()` (system block: `baseUrlToken`, `scope`) / `parse_app_mode_scope()` (apps' blocks: `scope`); unknown settings are rejected, not ignored |
| `dgen_definitions.py` | the whole emission spec (library domains, workspace, app runtime, app domains) and every output path |
| `dgen/libraries.py` | `build_library_layout` (names, collision refusal, placement), `library_package_files` (each library's `index.ts` + `package.json`) |
| `dgen/registrations.py` | `register_file_languages` / `register_context_namespaces` / `register_generator_target` (kind `"component"`) |
| `dgen/api.py` | `build_api_context`, `has_browser_routes`, path/query/body param contexts |
| `dgen/models.py` | `build_struct_context` / `build_entity_context` / `build_enum_context` + the three mutually exclusive closure predicates |
| `dgen/manifest.py` | `build_manifest_context`, `build_file_manifest`, `verify_file_manifest`, `build_readme` |
| `type_mappings.py` | `ANGULAR_TYPE_MAP`, extension maps, `apply_json_wire_overrides`, `UnmappedBuiltinTypeError` |
| typescript-core `web_client/type_resolution.py` | `resolve_route_type`, `resolve_closure_type_ref`, `check_type_map_completeness` |
| typescript-core `web_client/import_sites.py` | `ImportSite` — a contract import spelled relative inside its library, by package name across |
| typescript-core `web_client/local_names.py` | `allocate_local_names` — import aliasing and collision-free local names |
| `dgen/imports.py` | `merge_import_lines` — one line per module; the shared library's symbolic specifier spelled to the run's package |
| `ts_source.py` | Escapers/validators for emitted TypeScript (`escape_ts_string`, `require_ts_binding_identifier`, …) + `register_ts_source_filters` |
| `templates/` | `models/struct.ts.j2`, `models/enum.ts.j2`, `endpoints/client.ts.j2`, `core/*.ts.j2`, `manifest/*.ts.j2` |

### Emission Layout (from `dgen_definitions.py`)

```
per library (shared first, then each service):
domain library_models      → libs/{library}/src/lib/models/{container}/…
domain common_core         → libs/{system}-api-common/src/lib/core/{branded,page,query-params,request-options,api-base-url.token}.ts
                             + libs/{system}-api-common/src/lib/problem/problem.ts
domain common_exceptions   → libs/{system}-api-common/src/lib/problem/exceptions.ts
domain common_domain_errors→ libs/{system}-api-common/src/lib/problem/domain-errors.ts
domain service_clients     → libs/{service}-api/src/lib/clients/{api}.client.ts
domain service_manifest    → libs/{service}-api/src/lib/routes/route-manifest.ts + providers.ts
post-processing            → libs/{library}/src/index.ts + package.json
```

Iteration is over each library's **slice** of the contract's computed type closure (`each client_slice_type`) and **`each client_slice_api`** — never `each service { each struct }` and never separate `rest_api`/`serverless_block` clauses. A failure about a missing or extra emitted file is usually a placement/predicate question, not a template question.

### Test-to-Source Mapping

| Test file path | Source file path |
|---|---|
| `tests/unit/test_plugin.py` | `src/.../plugin.py` |
| `tests/unit/test_activation.py` | `src/.../activation.py` |
| `tests/unit/test_client_settings.py` | `src/.../client_settings.py` |
| `tests/unit/test_dgen_angular_defs.py`, `tests/unit/test_client_file_bindings.py` | `src/.../dgen_definitions.py` (+ `templates/`) |
| `tests/unit/dgen/test_api_context.py` | `src/.../dgen/api.py` |
| `tests/unit/dgen/test_models_context_builders.py` | `src/.../dgen/models.py` |
| `tests/unit/dgen/test_manifest.py` | `src/.../dgen/manifest.py` |
| `tests/unit/dgen/test_registrations.py` | `src/.../dgen/registrations.py` |
| `tests/unit/test_type_mappings.py` | `src/.../type_mappings.py` |
| `tests/unit/test_type_resolution.py` | typescript-core `web_client/type_resolution.py` |
| `tests/unit/dgen/test_libraries.py`, `tests/integration/test_client_libraries.py` | `src/.../dgen/libraries.py` |
| `tests/unit/test_hooks.py`, `tests/integration/test_library_compile.py` | `src/.../hooks.py` |
| `tests/unit/test_ts_string_escaping.py` | `src/.../ts_source.py` |
| `tests/integration/test_endpoint_emission.py` | `templates/endpoints/client.ts.j2` + `dgen/api.py` |
| `tests/integration/test_models_domain_emission.py` | `templates/models/*.ts.j2` + `dgen/models.py` |
| `tests/integration/test_manifest_emission.py` | `templates/manifest/*.ts.j2` + `dgen/manifest.py` |
| `tests/integration/test_hostile_text_emission.py` | `src/.../ts_source.py` escapers |
| `tests/integration/test_identifier_collision_emission.py` | typescript-core `web_client/local_names.py` |
| `tests/integration/test_generation_without_typescript.py` | `tests/integration/no_typescript_generation_probe.py` (subprocess probe) |
| `tests/unit/test_import_isolation.py` | static AST scan over `src/datrix_codegen_angular/` |

### Test Fixtures and Helpers

- `tests/conftest_shared.py` — `make_angular_context(backend_language, profile="test")` builds a `CodegenContext`. Vary `backend_language` to prove a rule is derived from the backend declaration rather than hardcoded.
- `tests/conftest.py` — `.dtrx`-backed application fixtures parsed through the real parser and semantic analyzer: `minimal_angular_app`, `app_with_angular_client`, `app_with_reachable_struct_and_enum`, `app_with_client_endpoints`, `app_with_unreachable_struct`. Fixture `.dtrx` sources live in `tests/fixtures/`.
- Real objects only — no mocks, no `SimpleNamespace`.

### No test compiles or runs the emitted client

The suite reads the emitted TypeScript as text; it never runs `npm`, `tsc`, `tsx` or `node` over it. What a compile would prove is held as a seam comparison over the emitted tree (every relative import names an emitted module), and what a run would prove is pinned on the emitted expression that decides it (for example, every URL interpolation is `this.base` or an `encodeURIComponent(...)` call).

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

The framework-neutral **client contract** — routes, params (DSL name *and* wire name), response type refs, provider sets, body encoding, pagination flags — lives in `datrix-codegen-common` (`generation/client_contract.py`), and the DAL generator compiler/executor and parity declarations live there too. A defect in any of those is fixed **there**, not worked around here — but that layer is consumed by EVERY generator, so a change to it must keep the changed behaviour's tagged tests green in every consuming package it reaches (CLAUDE.md's cross-surface impact rule). A per-frontend-target difference is a declared parameter or a renderer-local rendering step, never a target-name conditional in the shared layer — no frontend-target name may appear in a shared type, field, or alias.
