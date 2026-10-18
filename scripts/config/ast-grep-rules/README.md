# ast-grep Rules for Datrix

Structural Python rules for Datrix source audits. These rules complement the
Semgrep and LibCST scanners: use ast-grep for fast AST-shaped searches and use
LibCST when a finding needs format-preserving rewrites.

## Rules

| File | Pattern | Severity |
|------|---------|----------|
| `silent-fallback-none.yaml` | `dict.get(key, None)` | warning |
| `default-type-mapping-any.yaml` | `.get(..., "Any")` | error |
| `empty-except-pass.yaml` | `except ...: pass` | warning |
| `return-none-lookup.yaml` | lookup-style functions returning `None` | warning |
| `missing-encoding-read-text.yaml` | `Path.read_text()` without arguments | warning |
| `missing-encoding-write-text.yaml` | `Path.write_text(value)` without `encoding=` | warning |
| `open-without-encoding.yaml` | `open(path)` / `open(path, mode)` | warning |
| `codegen-string-append.yaml` | `code += ...` / `code = code + ...` | warning |
| `placeholder-function-body.yaml` | function body with only `pass` / ellipsis | warning |
| `placeholder-notimplemented-body.yaml` | body that raises `NotImplementedError` | warning |
| `generic-exception-raise.yaml` | `raise Exception(...)` | warning |
| `legacy-compatibility-call.yaml` | `legacy_*` / `*_compatibility` calls | warning |
| `banned-mock-import.yaml` | `from unittest.mock import ...` | error |
| `banned-simple-namespace.yaml` | `from types import SimpleNamespace` | error |
| `flattened-entity-iteration.yaml` | in generator sources: `app.all_entities()`, or one comprehension over `app.services.values()` then entities | error |
| `ad-hoc-plugin-registry.yaml` | `PluginRegistry()` in package sources and repo-tooling `scripts/**/lib/` modules, outside the test harness and `registry.py` | error |

`flattened-entity-iteration` holds the architecture cheat sheet's Entity Access rule (entities are
block-scoped; a generator iterates per service, per block). Its `files:` limits it to
`src/**/generators/` and `src/**/micro_generators/`, where an artifact must keep its owning
service; validators and app-wide lookups may walk every entity. `guard-code-standards.py` refuses
the same shapes when an edit adds them.

`ad-hoc-plugin-registry` holds the one process-wide plugin registry: production code reads it
through `plugin_registry()` (`datrix_common.plugin.registry`) and never builds its own, because
each `PluginRegistry()` rescans every installed distribution's entry points and is invisible to a
test that swaps `registry._PROCESS_REGISTRY`. The test harness (`datrix_testing`,
`datrix_codegen_common.testkit`) builds fresh registries on purpose and is ignored. The rule
covers the gate and script modules under `datrix/scripts/**/lib/` too (`ast-grep.ps1 datrix`
scans the showcase's `scripts/` tree): a gate self-test that needs fixture plugins installs them
with `datrix_testing.conformance.plugin_harness.process_fixture_plugin_environment` instead of
building a registry of its own.

## Usage

```powershell
# List available rules
.\scripts\scan\ast-grep.ps1 -ListRules

# Run one saved rule on all projects
.\scripts\scan\ast-grep.ps1 -All -Rule silent-fallback-none

# Run several saved rules
.\scripts\scan\ast-grep.ps1 -All -Rule default-type-mapping-any -Rule empty-except-pass

# Run a one-off pattern
.\scripts\scan\ast-grep.ps1 -All -Pattern 'raise Exception($MSG)'
```

PowerShell expands `$NAME` in double-quoted strings. Use single quotes for
ast-grep metavariable patterns.

