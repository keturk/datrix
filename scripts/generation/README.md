# Generation Scripts

Support around generated output: rebuilding the parser, refreshing example snapshots and seed
datasets, generation status and failure triage, evaluation scans of a generated project, and
cleanup of `.generated`. Generating a project itself is [`dev\generate.ps1`](../dev/README.md).
Every wrapper runs its Python from `lib/`. Command-by-command reference:
[quick-reference.md](quick-reference.md).

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/generation/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

## Scripts

| Script | Description |
|--------|-------------|
| `rebuild-parser.ps1` | Rebuild the Tree-sitter parser from `grammar.js` |
| `refresh-example-snapshot.ps1` | Regenerate one committed example snapshot |
| `refresh-seed-datasets.ps1` | Regenerate the builtin SeedDSL reference datasets |
| `status-generation.ps1` | Generation status from the latest `generate-results-*.log` |
| `triage-failures.ps1` | Group test/generation/deploy log failures by likely root cause |
| `compare-generated.ps1` | Feature-level comparison of `.generated` against `.generated_saved` |
| `evaluate-generated-scan.ps1` | Mechanical core of `/evaluate-generated` |
| `evaluate-service-scan.ps1` | Mechanical core of `/evaluate-generated-service` |
| `evaluate-services.ps1` | Run the per-service evaluation prompts in parallel |
| `delete-generated.ps1` | Rename `.generated` aside and delete it in the background |

## rebuild-parser.ps1

Rebuilds the Tree-sitter parser from `grammar.js`.

```powershell
# Normal rebuild (skips if unchanged)
.\rebuild-parser.ps1

# Force rebuild
.\rebuild-parser.ps1 -Force
```

Implementation: `scripts/generation/lib/rebuild_parser.py`, run in the shared venv. The parser's
own build machinery (`datrix_language.parser.tree_sitter_datrix.build`) names this wrapper as the
manual rebuild command.
