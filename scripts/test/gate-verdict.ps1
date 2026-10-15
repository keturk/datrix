#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Aggregate a GREEN/RED test gate verdict across Datrix packages.

.DESCRIPTION
 Runs gate_verdict.py in the shared venv. For each
 requested project (or all testable packages with -All), finds the newest
 test-results run and reports a per-project GREEN/RED verdict plus an overall
 verdict. Writes gate-verdict.json to <workspace>\.tmp\test\ by default.
 Exit code 0 only when every project is GREEN.

.PARAMETER Projects
 One or more project names (comma-separated or space-separated).

.PARAMETER All
 Check all testable datrix-* packages.

.PARAMETER Output
 Output JSON path (default <workspace>\.tmp\test\gate-verdict.json).

.PARAMETER SelfTest
 Run only the self-test: planted green, red and index-less run folders give
 GREEN, RED, RED. Reads no real run.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\gate-verdict.ps1 -Projects datrix-codegen-azure,datrix-language

.EXAMPLE
 .\gate-verdict.ps1 -SelfTest

.EXAMPLE
 .\gate-verdict.ps1 -All
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$Projects,

 [switch]$All,

 [string]$Output,

 [switch]$SelfTest,

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
foreach ($project in $Projects) {
 if ($project) { $pythonArgs += @("--projects", $project) }
}
if ($All) { $pythonArgs += "--all" }
if ($Output) { $pythonArgs += @("--output", $Output) }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\gate_verdict.py") -Arguments $pythonArgs -Gate "gate-verdict")
