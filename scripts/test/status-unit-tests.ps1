# PowerShell wrapper for status_unit_tests.py
# This script runs the Python unit test status checker

[CmdletBinding()]
param(
 [Alias("L")]
 [string]$Language,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

# Default: report only results under <workspace>\.generated
$pythonArgs = @("--root", (Join-Path (Get-DatrixWorkspaceRoot) ".generated"))
if (-not [string]::IsNullOrWhiteSpace($Language)) {
 # Restrict the report to <.generated>\<language>. The Python script validates the
 # name against the language directories actually present, never a hardcoded list.
 $pythonArgs += @("--language", $Language)
}
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\status_unit_tests.py") -Arguments $pythonArgs)
