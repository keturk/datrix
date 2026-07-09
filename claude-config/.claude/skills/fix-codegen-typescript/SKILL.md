---
description: Diagnose and fix datrix-codegen-typescript test failures, errors, and warnings from structured test results
model: sonnet
---

# Fix Codegen TypeScript

Diagnose and fix failures, errors, and warnings in `datrix-codegen-typescript` from a structured test-results `index.json`.

**Execute the shared playbook:** read `d:\datrix\.claude\skills\_shared\fix-package-playbook.md` and follow it exactly, with the parameters and package specifics below. The playbook owns the workflow (parse → errors → failures → warnings → verify → report), the index.json schema, abort conditions, and the cross-project handoff protocol.

## How to Invoke

```
/fix-codegen-typescript D:\datrix\datrix-codegen-typescript\.test_results\test-results-20260511-090734\index.json
```

The argument is the absolute path to an `index.json` inside a `.test_results/test-results-*/` directory.

## Parameters

- `{PACKAGE}` = `datrix-codegen-typescript`
- `{PACKAGE_PATH}` = `d:\datrix\datrix-codegen-typescript\`

## Package Specifics

- **Scope:** TypeScript codegen ONLY. Do NOT cross into Python codegen packages.
- **Package:** `datrix-codegen-typescript`
- **Fix target:** Generator source code, templates, transpiler, or test code — never generated output.

### Additional Test-to-Source Mapping

| Test file path | Source file path |
|---|---|
| `tests/unit/generators/entity/test_entity_generator.py` | `src/.../generators/entity/entity_generator.py` |
| `tests/unit/generators/api/test_endpoint_decorators_coverage.py` | `src/.../generators/api/_endpoint_decorators.py` |
| `tests/unit/transpiler/test_operators.py` | `src/.../transpiler/operators.py` |
| `tests/transpiler/test_ts_statements_coverage.py` | `src/.../transpiler/_transpiler_statements.py` + `_transpiler_expressions.py` |
| `tests/unit/test_validation.py` | `src/.../validation.py` |
| `tests/unit/test_type_resolver_coverage.py` | `src/.../type_resolver.py` |

### Critical Test Helper: ts_test_deps.py

Located at `tests/unit/generators/ts_test_deps.py`. Provides:

```python
build_template_generator()              # Returns TemplateGenerator with TS templates
build_ts_deps(service, app)             # Returns (TemplateGenerator, Transpiler, TypeResolver, OrmResolver, ServicePaths)
get_service(app, qualified_name)        # Lookup service by name
build_ts_entity_orchestrator(...)       # Returns EntityOrchestrator for tests
build_ts_schema_orchestrator(...)       # Returns SchemaOrchestrator for tests
build_ts_service_layer_orchestrator(...) # Returns ServiceLayerOrchestrator
build_ts_pubsub_orchestrator(...)       # Returns PubsubOrchestrator
build_ts_queue_orchestrator(...)        # Returns QueueOrchestrator
```

Also relevant for collection-time `TypeError` triage: `conftest.py`, `ts_test_deps.py`, or source.

### Key Entry Points

| File | Purpose |
|---|---|
| `plugin.py` | `TypeScriptGenerator` — main entry, creates transpiler, resolvers, orchestrators |
| `registry.py` | `TS_SUB_GENERATORS` — ordered list of sub-generators with feature gates |
| `type_resolver.py` | `TypeScriptTypeResolver` — Datrix types → TS types |
| `type_mappings.py` | `TYPESCRIPT_TYPE_MAP` — static type mapping dictionary |
| `profile.py` | `TS_PROFILE` — `LanguageProfile` for `SharedTranspiler` |
| `transpiler/ts_transpiler.py` | `SharedTranspilerTS` — DSL → TS visitor-based transpiler |
| `transpiler/builtins.py` | `TypeScriptBuiltinMethodMapper` — builtin method → TS code |

### Pipeline Architecture

```
.dtrx DSL → TreeSitterParser + Transformers → Application (validated AST)
  → TypeScriptGenerator.generate(app, output_dir)
    → For each Service:
        → Build: TemplateGenerator, SharedTranspilerTS, TypeScriptTypeResolver, OrmResolver
        → ServiceOrchestrator.generate_for_service()
            → EntityOrchestrator, SchemaOrchestrator, EndpointOrchestrator, ...
            → Each orchestrator: build context → render template → validate output
        → ProjectGenerator (package.json, tsconfig, app.module, main.ts)
    → generate_project_level(app):
        → LanguageWorkspaceGenerator, DeploymentTestGenerator, DocGenerator
```

### Trace Failures to Source (test setup / generator specifics)

- What is the test setting up? (DSL fixtures, mock data, orchestrators)
- What is being asserted? (generated code content, structure, imports)
- Trace: generator function → template context → template rendering (generator tests); visitor method → expression/statement handling → code emission (transpiler tests); type resolver → type mapping → output type string (type resolution tests)
- Root cause candidates: wrong logic in generator/transpiler code, missing case in a conditional/match, template error (Jinja2), incorrect type mapping, or outdated test expectation.

### Example test_id → path construction

`tests.transpiler.test_ts_statements_coverage.TestTypeResolution::test_unresolved_ref_type` → `tests/transpiler/test_ts_statements_coverage.py::TestTypeResolution::test_unresolved_ref_type`
