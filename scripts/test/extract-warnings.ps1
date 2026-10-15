#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Extract and deduplicate pytest warnings from a test run's full.log.

.DESCRIPTION
 Runs extract_warnings.py in the shared venv against
 a test-results run directory (or an index.json / full.log path inside one).
 Writes warnings.json into the run directory.

.PARAMETER Path
 Run directory, index.json path, or full.log path.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\extract-warnings.ps1 D:\datrix\datrix-codegen-aws\.test_results\test-results-20260712-121900
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Path,

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Path) { $pythonArgs += $Path }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\extract_warnings.py") -Arguments $pythonArgs)
