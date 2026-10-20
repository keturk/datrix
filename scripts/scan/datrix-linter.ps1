#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Lint Datrix .dtrx specification files using semantic analysis.

.DESCRIPTION
 The behaviour is datrix_scripts.scan.datrix_linter. Discovers system.dtrx entry points under
 the given paths and runs the full Datrix semantic analysis pipeline on each one. Reports all
 diagnostics (errors and warnings) with error codes, severities, messages, and source
 locations.

 Exit codes:
   0  No issues found
   1  One or more errors found (or warnings in -Strict mode); or neither -All nor a path
      (the usage is printed), or both

.PARAMETER Path
 One or more file or directory paths to scan (positional, variadic).
 Each may be a directory (scanned recursively for system.dtrx) or a direct
 path to a system.dtrx file.

.PARAMETER All
 Scan all subdirectories in the monorepo root for system.dtrx projects.
 Mutually exclusive with Path.

.PARAMETER Strict
 Treat warnings as errors. Exits with code 1 if any warnings are found.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER ResolveConfigs
 Enable service/shared .dcfg resolution before semantic checks.
 Disabled by default.

.PARAMETER Profile
 Config profile used when resolving service/shared .dcfg files (with -ResolveConfigs).
 Defaults to 'development'.

.PARAMETER SelfTest
 Run only the module's self-test: a planted broken system.dtrx fails the lint, the selection
 rules hold, and the wrapper seam holds.

.EXAMPLE
 .\datrix-linter.ps1 examples\01-foundation
 Lint the 01-foundation example project.

.EXAMPLE
 .\datrix-linter.ps1 -All
 Lint all Datrix projects in the monorepo.

.EXAMPLE
 .\datrix-linter.ps1 -All -Strict
 Lint all projects and fail on warnings too.

.EXAMPLE
 .\datrix-linter.ps1 datrix\examples\03-domains\ecommerce\system.dtrx
 Lint a specific system.dtrx file directly.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$Path,
 [Parameter(ParameterSetName = "Run")][switch]$All,
 [Parameter(ParameterSetName = "Run")][switch]$Strict,
 [switch]$Dbg,
 [Parameter(ParameterSetName = "Run")][switch]$ResolveConfigs,
 [Parameter(ParameterSetName = "Run")][string]$Profile = "development",
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.datrix_linter" -Parameters $PSBoundParameters
exit $LASTEXITCODE
