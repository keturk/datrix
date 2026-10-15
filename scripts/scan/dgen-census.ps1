#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Per-domain census of one dgen target's compiled DAL generator definitions.

.DESCRIPTION
 PowerShell wrapper for dgen_census.py. Walks every domain of the target's
 compiled GeneratorDefinition IR, counting declared file clauses (domain-level
 plus recursive iteration/children block files) and domain builders, and flags
 double-emit offenders (domains that declare files while keeping an imperative
 domain builder); any offender gates the exit code. The target name is resolved
 against the installed datrix.platforms / datrix.dgen_generator_targets
 entry points at runtime -- the target set is never hardcoded. Output:
 <workspace>\.tmp\dev\dgen-census-<language>.json.
 The script's own non-vacuity self-test (proves the double-emit comparator
 detects a forced synthetic defect and leaves a clean domain alone) runs
 automatically as step 1 of every invocation, including a real census; a
 self-test failure aborts before any real finding is reported. Pass
 -SelfTest to run only the self-test.

.PARAMETER Language
 Installed dgen target name (e.g. python). Unknown names fail loud listing
 every installed target. Not required with -SelfTest.

.PARAMETER Output
 Override the output JSON path.

.PARAMETER Dbg
 Enable debug logging in the Python script.

.PARAMETER SelfTest
 Run only the non-vacuity self-test (proves the double-emit comparator can
 detect a forced defect) and skip the real census; no
 -Language needed.

.EXAMPLE
 .\dgen-census.ps1 python

.EXAMPLE
 .\dgen-census.ps1 typescript -Output D:\datrix\.tmp\dev\ts-census.json

.EXAMPLE
 .\dgen-census.ps1 -SelfTest
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, Mandatory=$false)]
 [string]$Language,

 [Parameter()]
 [string]$Output,

 [Parameter()]
 [switch]$Dbg,

 [Parameter()]
 [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($SelfTest) {
 $pythonArgs += "--self-test"
} else {
 if (-not $Language) {
  Write-Host "Error: -Language is required unless -SelfTest is passed. Expected an installed dgen target, e.g. .\dgen-census.ps1 python." -ForegroundColor Red
  exit 2
 }
 $pythonArgs += @("--language", $Language)
 if ($Output) { $pythonArgs += @("--output", $Output) }
}
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\dgen_census.py") -Arguments $pythonArgs)
