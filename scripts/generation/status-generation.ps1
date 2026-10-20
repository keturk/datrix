#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Report generation status from the latest generate-results-*.log file.

.DESCRIPTION
 The behaviour is datrix_scripts.generation.status_generation. Finds the latest timestamped log
 under the results directory (default: <workspace>\.generated\.results) and lists which projects
 succeeded and failed. Use -ResultsDir when generate.ps1 wrote logs next to a custom output path
 or -OutputBase.

 Exit codes: 0 = no project failed, 1 = a project failed, or no results directory or log.

.PARAMETER ResultsDir
 Relative to workspace root, or an absolute path. Example:
 .generated\python\docker-compose\local\03-domains\ecommerce\python\.results

.PARAMETER SelfTest
 Run only the module's self-test: the latest planted log is read, a failure exits 1, and the
 wrapper seam holds.

.EXAMPLE
 .\status-generation.ps1
 Report the latest run under <workspace>\.generated\.results.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run")][string]$ResultsDir,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.generation.status_generation" -Parameters $PSBoundParameters
exit $LASTEXITCODE
