# Semgrep Rules for Datrix

Individual YAML rule files for the `.cursorrules` anti-pattern scanner.
Each file contains one (or a closely related set of) semgrep rule(s).

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/dev/semgrep.ps1" <args>`. See [scripts/README.md](../../README.md#bash-shell-invocation) for details.

## Rules

| File | Pattern | Severity |
|------|---------|----------|
| `silent-fallback-none.yaml` | `dict.get(key, None)` | WARNING |
| `default-type-mapping.yaml` | `type_map.get(t, "Any")` | ERROR |
| `empty-except-pass.yaml` | `except: pass` / `except Exception: pass` | WARNING |
| `missing-encoding-read.yaml` | `Path.read_text()` without `encoding=` | WARNING |
| `missing-encoding-write.yaml` | `Path.write_text()` without `encoding=` | WARNING |
| `banned-mock-import.yaml` | `from unittest.mock import ...` in tests | ERROR |
| `banned-simple-namespace.yaml` | `from types import SimpleNamespace` in tests | ERROR |
| `return-none-lookup.yaml` | `return None` in `get_*/find_*/lookup_*/resolve_*` | WARNING |
| `string-concat-codegen.yaml` | `code += f"..."` string concatenation | WARNING |
| `todo-comment.yaml` | `# TODO` comments | INFO |
| `magic-number-status.yaml` | Bare `200`/`404`/`500` in comparisons | WARNING |

## Usage

```powershell
# List all available rules
.\dev\semgrep.ps1 -ListRules

# Run all rules on all projects
.\dev\semgrep.ps1 -All

# Run a single rule to test it
.\dev\semgrep.ps1 -All -Rule empty-except-pass

# Run two specific rules
.\dev\semgrep.ps1 -All -Rule empty-except-pass -Rule return-none-lookup

# Run one rule on one project
.\dev\semgrep.ps1 datrix-common -Rule missing-encoding-read
```

## Adding New Rules

1. Create a new `.yaml` file in this directory
2. Follow semgrep rule syntax: https://semgrep.dev/docs/writing-rules/pattern-syntax
3. Use `datrix.` prefix for rule IDs
4. Test with `.\dev\semgrep.ps1 -All -Rule <your-rule-name>`
