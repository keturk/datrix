# Configuration Files

Shared configuration files used by scripts.

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/dev/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Files

| File / Directory | Description |
|------------------|-------------|
| `test-projects.json` | Project definitions for testing and code generation |
| `semgrep-rules/` | Individual YAML rule files for the Semgrep anti-pattern scanner |

## test-projects.json

Defines example projects organized by category for batch testing and generation.

### Structure

```json
{
 "description": "Shared project definitions for testing and generation",
 "defaultLanguage": "python",
 "defaultPlatform": "docker",
 "projects": {
 "tutorial": [...],
 "domains": [...]
 }
}
```

### Project Categories

| Category | Path | Description |
|----------|------|-------------|
| `tutorial` | `examples/01-tutorial/` | Step-by-step tutorial examples (23 projects) |
| `domains` | `examples/02-domains/` | Domain-specific examples (blog, ecommerce, healthcare) |
### Project Entry Format

```json
{
 "name": "01-basic-entity",
 "path": "examples/01-tutorial/01-basic-entity/system.dtrx",
 "description": "Basic entity with fields"
}
```

### Usage

Used by:
- `dev/generate.ps1` with `-All`, `-Tutorial`, `-Domains`, etc. flags
- `test/run-complete.ps1` for batch testing
- Python scripts via `library/shared/test_projects.py`

## semgrep-rules/

Individual YAML rule files for the Semgrep anti-pattern scanner (`dev/semgrep.ps1`). Each file defines one Semgrep rule that enforces a `.cursorrules` coding standard.

See [semgrep-rules/README.md](semgrep-rules/README.md) for the full rule catalog, usage examples, and instructions for adding new rules.

### Quick Usage

```powershell
# List all available rules
.\dev\semgrep.ps1 -ListRules

# Run all rules
.\dev\semgrep.ps1 -All

# Run a single rule
.\dev\semgrep.ps1 -All -Rule empty-except-pass
```
