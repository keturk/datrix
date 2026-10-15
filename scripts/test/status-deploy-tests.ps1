# PowerShell wrapper for status_deploy_tests.py
# This script runs the Python deployment test status checker

[CmdletBinding()]
param(
 [string]$Report,
 [Alias("L")]
 [string]$Language,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

# Default: report only results under <workspace>\.generated, always with the spec/integration breakdown
$pythonArgs = @("--root", (Join-Path (Get-DatrixWorkspaceRoot) ".generated"), "--detail")
if ($Report) { $pythonArgs += @("--report", $Report) }
if (-not [string]::IsNullOrWhiteSpace($Language)) {
 # Restrict the report to <.generated>\<language>. The Python script validates the
 # name against the language directories actually present, never a hardcoded list.
 $pythonArgs += @("--language", $Language)
}
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\status_deploy_tests.py") -Arguments $pythonArgs)
