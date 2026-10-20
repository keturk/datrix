#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if Python bytecode files are present under package src directories.

.DESCRIPTION
 The behaviour is datrix_scripts.scan.check_python_bytecode. Scans Datrix package src/ trees
 for .pyc/.pyo files and __pycache__ directories. The module needs only the standard library,
 and runs with PYTHONPYCACHEPREFIX outside every src/, so the check writes no bytecode itself.
 A src root outside BaseDir is refused.

 Exit codes: 0 no bytecode, 1 bytecode found, or a missing BaseDir or src directory, or a root
 outside BaseDir.

.PARAMETER BaseDir
 Monorepo root directory. Defaults to the parent workspace containing this script.

.PARAMETER ProjectDir
 Optional project names or paths to check. Defaults to all datrix package
 directories under BaseDir that have a src directory.

.PARAMETER SelfTest
 Run only the module's self-test: planted bytecode is listed, a clean tree passes, a missing
 src directory and a root outside BaseDir are refused, and the wrapper seam holds.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
    [Parameter(ParameterSetName = "Run")][string]$BaseDir,
    [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$ProjectDir,
    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.check_python_bytecode" -Parameters $PSBoundParameters
exit $LASTEXITCODE
