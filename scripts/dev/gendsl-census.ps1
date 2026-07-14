#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Per-domain census of one gendsl target's compiled genDSL definitions.

.DESCRIPTION
 PowerShell wrapper for gendsl_census.py. Walks every domain of the target's
 compiled GeneratorDefinition IR, counting declared file clauses (domain-level
 plus recursive iteration/children block files) and domain builders, and flags
 double-emit offenders (domains that declare files while keeping an imperative
 domain builder) and bridgeless declaring domains (no builder callable carries
 the MICRO_GENERATOR_CLS owning-class bridge). The target name is resolved
 against the installed datrix.platforms / datrix.gendsl_generator_targets
 entry points at runtime -- the target set is never hardcoded. Output:
 <workspace>\.tmp\dev\gendsl-census-<language>.json.

.PARAMETER Language
 Installed gendsl target name (e.g. python). Unknown names fail loud listing
 every installed target.

.PARAMETER Output
 Override the output JSON path.

.PARAMETER Dbg
 Enable debug logging in the Python script.

.EXAMPLE
 .\gendsl-census.ps1 python

.EXAMPLE
 .\gendsl-census.ps1 typescript -Output D:\datrix\.tmp\dev\ts-census.json
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, Mandatory=$true)]
 [string]$Language,

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
$pythonScript = Join-Path $libraryDir "dev\gendsl_census.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: gendsl_census.py not found at: $pythonScript"
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
 $pythonArgs = @($pythonScript, "--language", $Language)

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
