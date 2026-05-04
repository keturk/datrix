#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Detect leftover debug/logging artifacts in source code.

.DESCRIPTION
 Scans Python and TypeScript source files for common debug patterns that should not
 be committed: print() statements, console.log(), logger.warning/debug calls used
 as temporary instrumentation, breakpoint(), debugger statements, and TODO/FIXME
 markers tied to debugging sessions.

 Designed to run as a quick pre-commit or post-fix check to catch "debug scatter"
 before it breaks builds or pollutes the codebase.

 Exit codes:
   0 = clean (no debug artifacts found)
   1 = debug artifacts detected (prints details)
   2 = usage error

.PARAMETER ProjectDir
 One or more project directories to scan (positional). Can be names (e.g., datrix-common)
 or full paths.

.PARAMETER All
 Scan all datrix repositories.

.PARAMETER Strict
 Enable strict mode: also flag logger.debug() and logger.info() calls that contain
 variable interpolation (likely temporary debugging, not permanent logging).

.PARAMETER IncludeGenerated
 Also scan .generated/ directory (normally excluded to focus on source code).

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\check-debug-artifacts.ps1 datrix-codegen-python
 Scan one project for debug artifacts.

.EXAMPLE
 .\check-debug-artifacts.ps1 -All
 Scan all datrix repositories.

.EXAMPLE
 .\check-debug-artifacts.ps1 datrix-common -Strict
 Strict mode: also flag suspicious logger.debug/info with f-strings.
#>

[CmdletBinding()]
param(
 [Parameter()]
 [switch]$All,

 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$ProjectDir = @(),

 [Parameter()]
 [switch]$Strict,

 [Parameter()]
 [switch]$IncludeGenerated,

 [Parameter()]
 [switch]$Dbg
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\check_debug_artifacts.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Check if Python script exists
if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: check_debug_artifacts.py not found at: $pythonScript"
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

# Require -All or ProjectDir before activating venv
if (-not $All -and (-not $ProjectDir -or $ProjectDir.Count -eq 0)) {
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host "  .\check-debug-artifacts.ps1 -All" -ForegroundColor White
 Write-Host "  .\check-debug-artifacts.ps1 datrix-common [datrix-language ...]" -ForegroundColor White
 Write-Host "  .\check-debug-artifacts.ps1 D:\datrix\datrix-common" -ForegroundColor White
 Write-Host ""
 Write-Host "Use Get-Help .\check-debug-artifacts.ps1 -Full for detailed help." -ForegroundColor Yellow
 exit 2
}

# Main execution with proper error handling
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

 # Get workspace root for resolving relative project names
 $datrixWorkspaceRoot = Get-DatrixWorkspaceRoot

 # Determine which directories to check
 $pathsToCheck = @()
 if ($All) {
  $directories = Get-DatrixDirectoryPaths
  foreach ($dirPath in $directories) {
   if (Test-Path $dirPath) {
    $pathsToCheck += $dirPath
   }
  }
 } else {
  foreach ($p in $ProjectDir) {
   $fullPath = if ([System.IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $datrixWorkspaceRoot $p }
   if (Test-Path $fullPath) {
    $pathsToCheck += $fullPath
   } else {
    Write-Error "Path not found: $fullPath"
    exit 2
   }
  }
 }

 # Build arguments for Python script
 $pythonArgs = @($pythonScript) + $pathsToCheck
 if ($Strict) { $pythonArgs += "--strict" }
 if ($IncludeGenerated) { $pythonArgs += "--include-generated" }
 if ($Dbg) { $pythonArgs += "--debug" }

 # Run the Python script
 & $pythonExe @pythonArgs
 $exitCode = $LASTEXITCODE

 exit $exitCode

} catch {
 Write-Host ""
 Write-Host "Error occurred:" -ForegroundColor Red
 Write-Host $_.Exception.Message -ForegroundColor Red
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
