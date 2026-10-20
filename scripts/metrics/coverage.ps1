#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run pytest with coverage for one or more Datrix projects and show coverage details.

.DESCRIPTION
 Runs datrix_scripts.metrics.coverage for each project: the project's tests with pytest-cov,
 then the coverage report. Optionally fails if coverage is below a threshold (-FailUnder).
 The shared venv's package installs are checked first.

.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common\).

.PARAMETER All
 Run coverage for all Datrix projects (datrix-* folders, excluding datrix).

.PARAMETER Format
 Coverage report format: term, term-missing, html, xml. Default: term-missing.

.PARAMETER FailUnder
 Minimum coverage percentage; exit 1 if total coverage is below this value.

.PARAMETER StopOnError
 Stop on first project failure instead of continuing.

.PARAMETER VerboseOutput
 Enable verbose output from pytest.

.PARAMETER SelfTest
 Run only the module's self-test (planted projects; no test is run) and exit.

.EXAMPLE
 .\coverage.ps1 datrix-common
 Run tests with coverage for datrix-common (term-missing report).

.EXAMPLE
 .\coverage.ps1 datrix-common -Format html
 Run tests with coverage and generate HTML report.

.EXAMPLE
 .\coverage.ps1 -All -FailUnder 90
 Run coverage for all projects and fail if any project is below 90%.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [ValidateSet("term", "term-missing", "html", "xml")]
 [string]$Format = "term-missing",
 [float]$FailUnder = 0,
 [switch]$StopOnError,
 [switch]$VerboseOutput,
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.coverage" -Parameters $PSBoundParameters
exit $LASTEXITCODE
