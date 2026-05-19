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

## Usage

```powershell
# List available rules
.\scripts\dev\ast-grep.ps1 -ListRules

# Run one saved rule on all projects
.\scripts\dev\ast-grep.ps1 -All -Rule silent-fallback-none

# Run several saved rules
.\scripts\dev\ast-grep.ps1 -All -Rule default-type-mapping-any -Rule empty-except-pass

# Run a one-off pattern
.\scripts\dev\ast-grep.ps1 -All -Pattern 'raise Exception($MSG)'
```

PowerShell expands `$NAME` in double-quoted strings. Use single quotes for
ast-grep metavariable patterns.

