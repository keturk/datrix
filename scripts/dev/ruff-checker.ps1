#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Ruff Checker for Jinja2 Templates

.DESCRIPTION
 Finds Jinja templates in subfolders of the current directory, renders them with
 mock values in a temp folder, runs ruff check on the generated files, and saves
 findings in a report (ruff-report-TIMESTAMP.txt).

.EXAMPLE
 .\ruff-checker.ps1
 Check all .j2 templates in the current directory and subfolders.
#>

[CmdletBinding()]
param()

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\ruff_checker.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Check if Python script exists
if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: ruff_checker.py not found at: $pythonScript"
 exit 1
}

# Function to handle cleanup on exit
function Invoke-Cleanup {
 Disable-DatrixVenv
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

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

 # Check and install jinja2 if needed
 & $pythonExe -c "import jinja2" 2>&1 | Out-Null
 if ($LASTEXITCODE -ne 0) {
 Write-Host "Installing jinja2..." -ForegroundColor Yellow
 & $pythonExe -m pip install "jinja2>=3.0.0" | Out-Null
 if ($LASTEXITCODE -ne 0) {
 Write-Error "Failed to install jinja2. Please install manually: pip install jinja2>=3.0.0"
 exit 1
 }
 Write-Host "jinja2 installed successfully" -ForegroundColor Green
 }

 # Check and install ruff if needed
 & $pythonExe -c "import subprocess; subprocess.run(['ruff', '--version'], capture_output=True, check=True)" 2>&1 | Out-Null
 if ($LASTEXITCODE -ne 0) {
 Write-Host "Installing ruff..." -ForegroundColor Yellow
 & $pythonExe -m pip install "ruff>=0.1.0" | Out-Null
 if ($LASTEXITCODE -ne 0) {
 Write-Error "Failed to install ruff. Please install manually: pip install ruff>=0.1.0"
 exit 1
 }
 Write-Host "ruff installed successfully" -ForegroundColor Green
 }

 # Run the Python script
 Write-Host "Running ruff template checker..." -ForegroundColor Cyan
 Write-Host "Checking templates in: $(Get-Location)" -ForegroundColor Cyan
 Write-Host ""

 # Suppress PowerShell errors during Python execution - we check exit codes manually
 $oldErrorActionPreference = $ErrorActionPreference
 $ErrorActionPreference = "SilentlyContinue"
 $output = & $pythonExe $pythonScript 2>&1
 $exitCode = $LASTEXITCODE
 $ErrorActionPreference = $oldErrorActionPreference
 Write-Output $output

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
