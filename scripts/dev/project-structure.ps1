#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Generate .project-structure.md files for Datrix projects.

.DESCRIPTION
 Walks src/, tests/, and templates/ directories of each specified project and
 writes a .project-structure.md file to the project root containing annotated
 ASCII directory trees. Activates the datrix virtual environment and runs
 project_structure.py. Ensures virtual environment is deactivated even if the
 script is interrupted (Ctrl-C).

.PARAMETER Projects
 One or more project names (e.g., datrix-codegen-typescript) or paths.

.PARAMETER All
 Generate structure for all discoverable datrix-* projects.

.PARAMETER Depth
 Maximum directory depth to include in trees (default: 4).

.PARAMETER Dbg
 Enable debug logging in the Python script.

.EXAMPLE
 .\project-structure.ps1 datrix-codegen-typescript
 Generate structure file for the TypeScript codegen project.

.EXAMPLE
 .\project-structure.ps1 datrix-codegen-typescript datrix-codegen-python
 Generate structure files for multiple projects.

.EXAMPLE
 .\project-structure.ps1 -All
 Generate structure files for all discoverable projects.

.EXAMPLE
 .\project-structure.ps1 datrix-codegen-typescript -Depth 6
 Generate with deeper directory traversal.
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$Projects = @(),

 [Parameter()]
 [switch]$All,

 [Parameter()]
 [int]$Depth = 4,

 [Parameter()]
 [switch]$Dbg
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\project_structure.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Check if Python script exists
if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: project_structure.py not found at: $pythonScript"
 exit 1
}

# Function to handle cleanup on exit
function Invoke-Cleanup {
 Disable-DatrixVenv
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

# Trap Ctrl-C to ensure proper cleanup (PowerShell.Exiting may not fire on Ctrl-C)
trap {
 Write-Host ""
 Write-Warning "Interrupted by user (Ctrl-C)"
 Invoke-Cleanup
 exit 130
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

 # Build arguments for Python script
 $pythonArgs = @($pythonScript)

 if ($All) {
  $pythonArgs += "--all"
 } else {
  foreach ($proj in $Projects) {
   $pythonArgs += $proj
  }
 }

 $pythonArgs += "--depth"
 $pythonArgs += $Depth.ToString()

 if ($Dbg) {
  $pythonArgs += "--debug"
 }

 # Run the Python script
 & $pythonExe @pythonArgs
 $exitCode = $LASTEXITCODE

 # Exit with the same code as the Python script
 exit $exitCode

} catch {
 Write-Host ""
 Write-Host "Error occurred:" -ForegroundColor Red
 Write-Host $_.Exception.Message -ForegroundColor Red
 Write-Host ""
 if ($_.Exception.InnerException) {
  Write-Host "Inner exception:" -ForegroundColor Red
  Write-Host $_.Exception.InnerException.Message -ForegroundColor Red
  Write-Host ""
 }
 Invoke-Cleanup
 exit 1
} finally {
 # Ensure virtual environment is deactivated even on Ctrl-C
 Invoke-Cleanup
}
