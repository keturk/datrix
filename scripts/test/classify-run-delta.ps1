#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Classify the delta between two structured test-results runs.

.DESCRIPTION
 Activates the Datrix virtual environment and runs datrix_scripts.classify_run_delta.
 Compares the failing sets and cluster patterns of a previous and a current
 run of the same project, writes run-delta.json into the CURRENT run
 directory, and reports a verdict (SUCCESS / PARTIAL / NO_CHANGE /
 REGRESSION). Exit code 0 only for SUCCESS.

.PARAMETER Previous
 Previous run directory or index.json path (also accepted as the first
 positional argument).

.PARAMETER Current
 Current run directory or index.json path (also accepted as the second
 positional argument).

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\classify-run-delta.ps1 -Previous D:\datrix\datrix-codegen-aws\.test_results\test-results-20260712-235813 -Current D:\datrix\datrix-codegen-aws\.test_results\test-results-20260713-000700

.EXAMPLE
 .\classify-run-delta.ps1 <previous-run-dir> <current-run-dir>
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Previous,

 [Parameter(Position=1)]
 [string]$Current,

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Previous) { $pythonArgs += @("--previous", $Previous) }
if ($Current) { $pythonArgs += @("--current", $Current) }
if ($Dbg) { $pythonArgs += "--debug" }

# Shared with the red-run digest, so it lives in the shared scripts package and runs as a module.
exit (Invoke-DatrixPythonScript -Module "datrix_scripts.classify_run_delta" -Arguments $pythonArgs)
