#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Declarative design-acceptance assertion runner over a file tree.

.DESCRIPTION
 PowerShell wrapper for conformance_gate.py. Evaluates a JSON spec of
 must_contain / must_not_contain / file_exists / file_absent / count_equals
 assertions (regex patterns, text files only) over a target tree and writes a
 per-assertion PASS/FAIL ledger to
 <workspace>\.test-output\conformance\<spec-stem>-ledger.json.
 must_not_contain supports a negative_control tree: the pattern MUST appear
 there or the assertion fails as vacuous. A built-in self-test proving every
 assertion type both detects a violation and passes a satisfied case runs as
 step 1 of every invocation (self-test failure aborts with exit 2).

.PARAMETER Spec
 Path to the conformance spec JSON.

.PARAMETER SelfTest
 Run only the built-in self-test and exit.

.PARAMETER Dbg
 Enable debug logging in the Python script.

.EXAMPLE
 .\conformance-gate.ps1 my-spec.json

.EXAMPLE
 .\conformance-gate.ps1 -SelfTest
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Spec,

 [Parameter()]
 [switch]$SelfTest,

 [Parameter()]
 [string]$Output,

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\conformance_gate.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: conformance_gate.py not found at: $pythonScript"
 exit 1
}

# Function to handle cleanup on exit
function Invoke-Cleanup {
 Disable-DatrixVenv
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

# Trap Ctrl-C to ensure proper cleanup
trap {
 Write-Host ""
 Write-Warning "Interrupted by user (Ctrl-C)"
 Invoke-Cleanup
 exit 130
}

try {
 # Activate virtual environment
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
  Write-Error "Failed to activate virtual environment"
  exit 1
 }

 # Get Python executable from venv
 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"

 # Build arguments for Python script
 $pythonArgs = @($pythonScript)

 if ($Spec) {
  $pythonArgs += "--spec"
  $pythonArgs += $Spec
 }
 if ($SelfTest) {
  $pythonArgs += "--self-test"
 }
 if ($Output) {
  $pythonArgs += "--output"
  $pythonArgs += $Output
 }
 if ($Dbg) {
  $pythonArgs += "--debug"
 }

 & $pythonExe @pythonArgs
 exit $LASTEXITCODE

} catch {
 Write-Host ""
 Write-Host "Error occurred:" -ForegroundColor Red
 Write-Host $_.Exception.Message -ForegroundColor Red
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
