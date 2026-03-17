#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Syntax Checker for Datrix .dtrx Files

.DESCRIPTION
 Validates the syntax of .dtrx files using the tree-sitter parser.
 Activates the datrix virtual environment, installs required dependencies,
 and runs syntax_checker.py. Ensures virtual environment is deactivated even
 if the script is interrupted (Ctrl-C).

.PARAMETER Path
 File or directory to check (default: all datrix repositories).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\syntax-checker.ps1
 Check all .dtrx files in all datrix repositories.

.EXAMPLE
 .\syntax-checker.ps1 path/to/file.dtrx
 Check a single file.

.EXAMPLE
 .\syntax-checker.ps1 examples/
 Check all .dtrx files in examples directory.

.EXAMPLE
 .\syntax-checker.ps1 . -Dbg
 Check with debug logging enabled.
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Path = "",

 [Parameter()]
 [switch]$Dbg
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\syntax_checker.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Get datrix root and workspace root
$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRoot

# Check if Python script exists
if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: syntax_checker.py not found at: $pythonScript"
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

 # Check and install tree-sitter if needed (avoid pipeline to preserve $LASTEXITCODE)
 $null = & $pythonExe -c "import tree_sitter" 2>&1
 if ($LASTEXITCODE -ne 0) {
 Write-Host "Installing tree-sitter..." -ForegroundColor Yellow
 $null = & $pythonExe -m pip install "tree-sitter>=0.23.0" 2>&1
 if ($LASTEXITCODE -ne 0) {
 Write-Error "Failed to install tree-sitter. Please install manually: pip install tree-sitter>=0.23.0"
 exit 1
 }
 Write-Host "tree-sitter installed successfully" -ForegroundColor Green
 }

 # Determine which directories to check
 $pathsToCheck = @()
 if ([string]::IsNullOrEmpty($Path)) {
 # Default: check all datrix repositories
 $directories = Get-DatrixDirectoryPaths
 foreach ($dirPath in $directories) {
 if (Test-Path $dirPath) {
 $pathsToCheck += $dirPath
 }
 }
 } else {
 $pathsToCheck = @($Path)
 }

 # Build arguments for Python script
 $pythonArgs = @($pythonScript) + $pathsToCheck
 if ($Dbg) {
 $pythonArgs += "--debug"
 }

 # Run the Python script
 Write-Host "Running syntax checker..." -ForegroundColor Cyan
 Write-Host ""

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
