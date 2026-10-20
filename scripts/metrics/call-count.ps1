#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Count calls to named functions (and subprocess launches) while one workload runs in-process.

.DESCRIPTION
 Runs datrix_scripts.metrics.call_count in the shared venv. The workload is one `datrix generate`
 of -Source in -Language (output under <workspace>\.tmp\call-count\), or importing the -Import
 modules. Counters are installed before any workload module loads, so names bound at import time
 are counted too. Prints the counts, the wall time and one verdict line; -Expect bounds make it
 exit 1 when a count is out of bounds. A self-test of the counter runs first on every invocation
 (exit 2 if it fails).

.PARAMETER Source
 system.dtrx (or project folder) to generate. Needs -Language.

.PARAMETER Language
 Generation language: any registered datrix.languages target.

.PARAMETER Import
 Comma-separated modules to import instead of generating.

.PARAMETER Count
 Comma-separated targets, module:qualname (e.g. importlib.metadata:entry_points).

.PARAMETER Expect
 Comma-separated bounds <target><op><n>, op one of <=, ==, >= ("subprocess" names the launch count).

.PARAMETER Json
 Also write the result JSON to this path.

.PARAMETER SelfTest
 Run only the counter self-test and the wrapper seam checks.

.EXAMPLE
 .\call-count.ps1 -Source datrix/examples/03-domains/ecommerce/system.dtrx -Language python -Count "importlib.metadata:entry_points" -Expect "importlib.metadata:entry_points<=5"

.EXAMPLE
 .\call-count.ps1 -Import datrix_codegen_aws -Count "datrix_codegen_kernel.dgen.compiler:generator_definition_file" -Expect "datrix_codegen_kernel.dgen.compiler:generator_definition_file==0"
#>
[CmdletBinding()]
param(
 [string]$Source, [string]$Language, [string]$Import, [string]$Count, [string]$Expect, [string]$Json, [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.call_count" -Parameters $PSBoundParameters
exit $LASTEXITCODE
