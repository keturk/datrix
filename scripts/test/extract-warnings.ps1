#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Extract and deduplicate pytest warnings from a test run's full.log.
.DESCRIPTION
 Runs datrix_scripts.test.extract_warnings against a test-results run directory (or an index.json / full.log
 path inside one) and writes warnings.json into the run directory. Exit 0 when done, 2 on a usage error.
 -SelfTest runs the module's self-test. python -m datrix_scripts.test.extract_warnings --help describes every option.
.EXAMPLE
 .\test\extract-warnings.ps1 D:\datrix\datrix-codegen-aws\.test_results\test-results-20260712-121900
#>
[CmdletBinding()]
param(
 [Parameter(Position=0)][string]$Path, [switch]$Dbg, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.extract_warnings" -Parameters $PSBoundParameters
exit $LASTEXITCODE
