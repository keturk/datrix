# Development Scripts

Generation, and the tools agents read the codebase through: the code index, the local model
servers, the knowledge base (`ineedtoknow`), documentation checks and code-health digests, with
the gates that hold each of them. Every wrapper runs its Python from `lib/`. Command-by-command
reference: [quick-reference.md](quick-reference.md).

> **Bash shell:** Examples below use PowerShell syntax. For bash, use `powershell -File "d:/datrix/datrix/scripts/dev/<script>.ps1" <args>`. See [scripts/README.md](../README.md#bash-shell-invocation) for details.

Neighbouring folders took the rest of what used to live here: static scans in [../scan/](../scan/README.md),
generation support (parser rebuild, snapshots, triage, evaluation, cleanup) in
[../generation/](../generation/README.md), workspace listing and cleanup in
[../workspace/](../workspace/quick-reference.md), codemods in [../codemods/](../codemods/README.md).

## Scripts

| Script | Description |
|--------|-------------|
| `generate.ps1` | Generate code from .dtrx source files |
| `generate-doc-fragments.ps1` | Generate documentation fragments from source |
| `check-docs.ps1` | Lint documentation for common drift patterns |
| `code-index.ps1` | Query the code index; `-Setup` registers its MCP server |
| `code-index-gate.ps1` | Behaviour checks for the code index |
| `logic-map-report.ps1` | Dump the logic map to a Markdown report |
| `local-llm.ps1` | Set up, inspect and measure the local model servers; `-Setup` registers their MCP server |
| `local-llm-gate.ps1` | Behaviour checks for the local-model reading tools |
| `ineedtoknow.ps1` | Ask the knowledge base a question in your own words |
| `ineedtoknow-gate.ps1` | Behaviour checks for the knowledge base |
| `code-scan.ps1` | On-demand code-health digest for changed packages |
| `generate-test-rules.ps1` | Propose and apply `@test-rule` annotations with a local model |

## generate.ps1

Main code generation script. Generates Python/TypeScript code from .dtrx source files.

### Single Project Mode

```powershell
# Basic generation
.\generate.ps1 examples/01-foundation/system.dtrx .generated/python/docker/my-project

# With custom language and platform
.\generate.ps1 examples/01-foundation/system.dtrx .generated/typescript/azure-container-apps/my-project -L typescript -P azure-container-apps

# Enable debug logging
.\generate.ps1 examples/01-foundation/system.dtrx .generated/python/docker/my-project -Dbg
```

### Batch Mode

```powershell
# Generate all examples
.\generate.ps1 -All

# Generate specific category
.\generate.ps1 -TestSet foundation -L python  # examples/01-foundation
.\generate.ps1 -Domains # examples/03-domains
# With options
.\generate.ps1 -All -Language typescript -Runtime azure-app-service -ConfigProfile pilot
```

### Parameters

| Parameter | Alias | Default | Description |
|-----------|-------|---------|-------------|
| `-Source` | | | Path to .dtrx file (single mode) |
| `-Output` | | | Output directory (single mode) |
| `-All` | | | Generate all projects |
| `-TestSet` | | `all` | Test set name (batch mode) |
| `-Domains` | | | Generate domain examples only |
| `-Language` | `-L` | `python` | Target language (python, typescript), output-path segment |
| `-Runtime` | `-R` | (config) | Output-path runtime segment (docker-compose, azure-container-apps, azure-app-service, ecs-fargate, app-runner) |
| `-ConfigProfile` | | `test` | Config profile that selects the deployment target; also selects the provider segment read from `config/system.dcfg` |
| `-OutputBase` | | `.generated` | Output base directory (batch mode) |
| `-Dbg` | | | Enable debug logging |

The output-path provider segment (`local`/`existing`/`aws`/`azure`) is read from each project's `config/system.dcfg` deployment block for the active `-ConfigProfile`; it is not a flag.

### Logs

Generation logs are saved to `.generated/.results/generate-results-TIMESTAMP-LANGUAGE[-PROFILE].log`. Old logs are not deleted automatically.

The language and profile segments are labels, not what keeps two runs apart: each run
**claims** its log file (`common/DatrixRunLog.psm1`), so two runs that compute the same
name — two profiles generated in the same second, or two runs of one profile — get
`…-2.log`, `…-3.log`, … rather than truncating and interleaving one file. Held by
`test/run-log-exclusivity-gate.ps1`.

### Implementation

- **PowerShell:** `scripts/dev/generate.ps1` — Activates the venv, ensures the packages, claims the run log, runs the generator.
- **Python:** `scripts/dev/lib/generate.py` — Resolves the output path and runs `datrix generate` per project.
