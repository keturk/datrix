# PowerShell wrapper for datrix_scripts.status_tests
# This script runs the Python test status checker

[CmdletBinding()]
param(
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Dbg) { $pythonArgs += "--debug" }

# Shared with the test runner and the tooling gates, so it lives in the shared scripts package
# and runs as a module.
exit (Invoke-DatrixPythonScript -Module "datrix_scripts.status_tests" -Arguments $pythonArgs)
