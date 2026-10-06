# PowerShell wrapper for datrix_scripts.status_tests
# This script runs the Python test status checker

[CmdletBinding()]
param(
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\common"
# Shared with the test runner and the tooling gates, so it lives in the shared scripts package
# and runs as a module.
$PythonModule = "datrix_scripts.status_tests"
$PythonScript = Join-Path $commonDir "lib\datrix_scripts\status_tests.py"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Function to handle cleanup on exit
function Invoke-Cleanup {
 Disable-DatrixVenv
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

# Main execution with proper error handling
try {
 # Ensure virtual environment is activated
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
 Write-Error "Failed to activate virtual environment"
 exit 1
 }

 # Get Python executable from venv
 $venvPath = Get-DatrixVenvPath
 $PythonExe = Join-Path $venvPath "Scripts\python.exe"

 # Check if the Python script exists
 if (-not (Test-Path $PythonScript)) {
 Write-Error "Python script not found: $PythonScript"
 exit 1
 }

 # Build arguments for Python script
 $pythonArgs = @("-m", $PythonModule)
 if ($Dbg) {
 $pythonArgs += "--debug"
 }

 # Run the Python script
 Write-Host "Running test status checker..." -ForegroundColor Cyan
 Write-Host ""

 & $PythonExe @pythonArgs

 # Capture exit code
 $ExitCode = $LASTEXITCODE

 # Exit with the same code as the Python script
 exit $ExitCode

} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 # Ensure virtual environment is deactivated even on Ctrl-C
 Invoke-Cleanup
}
