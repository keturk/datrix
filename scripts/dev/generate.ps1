#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Generate Datrix Projects

.DESCRIPTION
 The behaviour is datrix_scripts.dev.generate. Generates Datrix projects from source files, in
 single-project or batch mode:
 1. Single project: source file (output folder optional; derived from test-projects.json when omitted)
 2. -All: all projects (test set all)
 3. -Domains: examples/02-domains

 Batch modes use the same unified generation pipeline for consistent behavior.
 Before generating, the run checks the package installs, that every plugin loads and that the
 datrix command runs (reinstalling datrix-cli once when it does not), and validates -Language
 against the installed datrix.languages set.
 Timestamped generate-results-*.log files are always written to .generated/.results at the
 workspace (monorepo) root, regardless of -OutputBase or project output path.

 Exit codes: the generation's; 1 when the run could not start (no language, an unregistered one,
 neither a source nor a batch, a missing source, a failed install, plugin or datrix command check).

.PARAMETER Source
 Path to source .dtrx file (positional, required for single project mode).

.PARAMETER Output
 Output directory path (positional, optional for single project mode). When omitted, derived from test-projects.json (defaultLanguage, defaultPlatform) and the source path.

.PARAMETER All
 Generate all projects from the specified test set (switch parameter).

.PARAMETER Domains
 Generate only domain examples (examples/02-domains). Uses test set domains.

.PARAMETER Language
 Target generation language (required). Accepts any registered datrix.languages
 target, validated at runtime against the installed set (never a hardcoded
 python/typescript list). Forwarded to `datrix generate --language` as the real
 generation target -- it also selects the output-path language segment, so the
 two can never disagree.
 Can be abbreviated as -L.

.PARAMETER Runtime
 Optional runtime for output path derivation (options: docker-compose, azure-container-apps, azure-app-service, ecs-fargate, app-runner).
 The actual runtime used for generation comes from the config/system.dcfg deployment block of the active profile -- NOT from this flag.
 Can be abbreviated as -R.

.PARAMETER ConfigProfile
  Config (.dcfg) profile that selects the deployment target (e.g. test, development, staging, production, pilot).
  This is the ONLY flag that changes what is generated. When omitted, datrix generate uses its default profile 'test',
  which typically extends the docker-compose base -- so omitting it on an Azure project yields docker output.
  Pass the profile that targets your runtime (e.g. -ConfigProfile pilot) to generate the Azure variant.

.PARAMETER OutputBase
 Output base directory (default: .generated). Only used with -All parameter.

.PARAMETER TestSet
 Test set to use (default: all). Only used with -All parameter.

.PARAMETER ValidationLevel
 Post-generation validation level, forwarded to `datrix generate --validation-level`
 (none, fast or standard; the CLI validates the value and owns the default, standard).
 When omitted, no flag is passed.

.PARAMETER VerboseOutput
 Enable verbose output. When not specified, minimal output is shown (summary only).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the module's self-test: the generation arguments per mode, the output filter, the
 summary, the language check, and the wrapper seam. Generates nothing.

.EXAMPLE
 .\generate.ps1 examples/02-features/01-core-data-modeling/entities/system.dtrx -L python
 Generate a single project; output path derived from test-projects.json.

.EXAMPLE
 .\generate.ps1 examples/02-features/01-core-data-modeling/entities/system.dtrx .generated/python/docker/my-project -L python
 Generate a single project with explicit output path (python, docker).

.EXAMPLE
 .\generate.ps1 -All -L python
 Generate all projects for Python.

.EXAMPLE
 .\generate.ps1 -All -Language typescript -Runtime azure-app-service -ConfigProfile pilot
 Generate all projects for TypeScript; the output-path provider segment is read from each
 project's config/system.dcfg deployment block for the 'pilot' profile.

.EXAMPLE
 .\generate.ps1 -Domains -L typescript
 Generate only domain examples (02-domains folder) for TypeScript.
#>

[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ParameterSetName = "Run")][string]$Source,
 [Parameter(Position = 1, ParameterSetName = "Run")][string]$Output,
 [Parameter(ParameterSetName = "Run")][switch]$All,
 [Parameter(ParameterSetName = "Run")][switch]$Domains,
 [Parameter(ParameterSetName = "Run")][Alias("L")][string]$Language,
 [Parameter(ParameterSetName = "Run")][Alias("R")][ValidateSet("docker-compose", "azure-container-apps", "azure-app-service", "ecs-fargate", "app-runner")][string]$Runtime,
 [Parameter(ParameterSetName = "Run")][string]$ConfigProfile,
 [Parameter(ParameterSetName = "Run")][string]$OutputBase = ".generated",
 [Parameter(ParameterSetName = "Run")][string]$TestSet = "all",
 [Parameter(ParameterSetName = "Run")][string]$ValidationLevel,
 [Parameter(ParameterSetName = "Run")][switch]$VerboseOutput,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.generate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
