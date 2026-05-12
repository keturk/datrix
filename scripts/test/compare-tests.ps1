#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Compare timestamped test results inside one .test_results folder.

.DESCRIPTION
 Activates the Datrix virtual environment and runs compare_tests.py against a
 single project .test_results directory. Unit test runs are compared only with
 other unit-test timestamps, and deploy test runs are compared only with other
 deploy-test timestamps.

.PARAMETER TestResults
 Path to a single .test_results folder.

.PARAMETER Report
 Optional Markdown report path.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\compare-tests.ps1 D:\datrix\.projects\curvaero\python\.test_results

.EXAMPLE
 .\compare-tests.ps1 D:\datrix\.projects\curvaero\python\.test_results -Report D:\datrix\curvaero-test-comparison.md
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, Mandatory=$true)]
 [Alias("Path")]
 [string]$TestResults,

 [string]$Report,

 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "test\compare_tests.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

function Invoke-Cleanup {
 Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 $resolvedTestResults = Resolve-Path -LiteralPath $TestResults -ErrorAction Stop
 $resolvedTestResultsPath = $resolvedTestResults.Path
 if (-not (Test-Path -LiteralPath $resolvedTestResultsPath -PathType Container)) {
 Write-Error "Test results path is not a directory: $resolvedTestResultsPath"
 exit 1
 }
 if ((Split-Path -Leaf $resolvedTestResultsPath) -ne ".test_results") {
 Write-Error "Expected a .test_results folder, got: $resolvedTestResultsPath"
 exit 1
 }

 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
 Write-Error "Failed to activate virtual environment"
 exit 1
 }

 $venvPath = Get-DatrixVenvPath
 $PythonExe = Join-Path $venvPath "Scripts\python.exe"

 if (-not (Test-Path -LiteralPath $PythonScript)) {
 Write-Error "Python script not found: $PythonScript"
 exit 1
 }

 $pythonArgs = @($PythonScript, "--test-results", $resolvedTestResultsPath)
 if ($Report) {
 $pythonArgs += @("--report", $Report)
 }
 if ($Dbg) {
 $pythonArgs += "--debug"
 }

 Write-Host "Running test comparison report..." -ForegroundColor Cyan
 Write-Host ""

 & $PythonExe @pythonArgs
 $ExitCode = $LASTEXITCODE
 exit $ExitCode

} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
