#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Prove a code change is output-neutral: generate examples twice (BEFORE code
 state vs working tree) and byte-diff the two trees.

.DESCRIPTION
 PowerShell wrapper for byte_identity_generate.py. The BEFORE state comes from
 a READ-ONLY git archive snapshot of the named packages at a ref (-BeforeRef +
 -Packages), or from a caller-supplied prebuilt source overlay (-BeforeTree);
 either is applied via PYTHONPATH in a dedicated worker subprocess. The two
 output roots are fixed equal-length paths (.test-output/byte-identity/bef and
 aft) -- the ruff post-format hook batches by command-line length, so unequal
 roots would produce phantom diffs.

.PARAMETER Example
 One or more example dirs relative to datrix/examples (repeatable or
 comma-separated), e.g. 01-foundation. Exactly one of -Example / -TestSet.

.PARAMETER TestSet
 Named test set from scripts/config/test-projects.json.

.PARAMETER BeforeRef
 Git ref for the BEFORE code state (read-only git archive; requires -Packages).

.PARAMETER Packages
 Package directory names (own git repos) snapshotted at -BeforeRef
 (repeatable or comma-separated).

.PARAMETER BeforeTree
 Prebuilt BEFORE source overlay directory (prepended to the worker PYTHONPATH).

.PARAMETER Output
 Override the report.json path (report.md lands next to it).

.PARAMETER Dbg
 Enable debug logging in the Python script.

.EXAMPLE
 .\byte-identity-generate.ps1 -Example 01-foundation -BeforeRef HEAD -Packages datrix-codegen-common

.EXAMPLE
 .\byte-identity-generate.ps1 -Example 01-foundation -BeforeTree D:\datrix\.tmp\my-before\src
#>

[CmdletBinding()]
param(
 [Parameter()]
 [string[]]$Example = @(),

 [Parameter()]
 [string]$TestSet,

 [Parameter()]
 [string]$BeforeRef,

 [Parameter()]
 [string[]]$Packages = @(),

 [Parameter()]
 [string]$BeforeTree,

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
$pythonScript = Join-Path $libraryDir "dev\byte_identity_generate.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: byte_identity_generate.py not found at: $pythonScript"
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

 foreach ($ex in $Example) {
  $pythonArgs += "--example"
  $pythonArgs += $ex
 }
 if ($TestSet) {
  $pythonArgs += "--test-set"
  $pythonArgs += $TestSet
 }
 if ($BeforeRef) {
  $pythonArgs += "--before-ref"
  $pythonArgs += $BeforeRef
 }
 if ($Packages.Count -gt 0) {
  $pythonArgs += "--packages"
  $pythonArgs += ($Packages -join ",")
 }
 if ($BeforeTree) {
  $pythonArgs += "--before-tree"
  $pythonArgs += $BeforeTree
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
