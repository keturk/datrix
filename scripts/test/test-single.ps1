#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run a single test file or pattern quickly for checkpoint-based debugging.

.DESCRIPTION
 Lightweight test runner for verifying individual fixes. Activates the datrix virtual
 environment and runs pytest against a specific test file, test class, or test function.
 Designed for the fix-one-verify-one workflow where you need fast feedback on a single fix.

 Unlike test.ps1 which orchestrates full project test runs, this script focuses on
 running exactly what you specify with minimal overhead.

 Exit codes:
   0 = tests passed
   1 = tests failed
   2 = usage error

.PARAMETER TestPath
 Path to the test file, or a pytest node ID (file::class::method). Can be:
   - Full path: D:\datrix\datrix-codegen-python\tests\test_entity.py
   - Relative path: tests\test_entity.py (resolved against Project)
   - Node ID: tests/test_entity.py::TestEntityGen::test_basic

.PARAMETER Project
 Project context for resolving relative paths. Defaults to auto-detect from TestPath.

.PARAMETER Keyword
 Pytest -k filter expression (e.g., "test_enum and not test_enum_import").

.PARAMETER Marker
 Pytest -m marker filter (e.g., "not slow").

.PARAMETER VerboseOutput
 Show full pytest output (default: quiet mode with failure details only).

.PARAMETER FailFast
 Stop on first failure (-x flag).

.PARAMETER SkipInstall
 Skip pip install verification. Requires a ready .venv.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\test-single.ps1 "D:\datrix\datrix-codegen-python\tests\generators\test_entity_generator.py"
 Run all tests in a specific file.

.EXAMPLE
 .\test-single.ps1 "tests/generators/test_entity_generator.py::TestEntityGenerator::test_basic" -Project datrix-codegen-python
 Run a single test method.

.EXAMPLE
 .\test-single.ps1 -Project datrix-common -Keyword "test_poly_string"
 Run tests matching a keyword in a project.

.EXAMPLE
 .\test-single.ps1 "tests/test_enum.py" -Project datrix-codegen-typescript -FailFast
 Run tests in a file, stop on first failure.
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$TestPath = "",

 [Parameter()]
 [string]$Project = "",

 [Parameter()]
 [string]$Keyword = "",

 [Parameter()]
 [string]$Marker = "",

 [Parameter()]
 [switch]$VerboseOutput,

 [Parameter()]
 [switch]$FailFast,

 [Parameter()]
 [switch]$SkipInstall,

 [Parameter()]
 [switch]$Dbg
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "test\test_single.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Check if Python script exists
if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: test_single.py not found at: $pythonScript"
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

# Require TestPath or Keyword
if (-not $TestPath -and -not $Keyword) {
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host "  .\test-single.ps1 <test-path> [-Project <name>]" -ForegroundColor White
 Write-Host "  .\test-single.ps1 -Project <name> -Keyword <expr>" -ForegroundColor White
 Write-Host ""
 Write-Host "Examples:" -ForegroundColor Cyan
 Write-Host "  .\test-single.ps1 tests/test_foo.py -Project datrix-common"
 Write-Host "  .\test-single.ps1 -Project datrix-codegen-python -Keyword test_enum"
 Write-Host ""
 Write-Host "Use Get-Help .\test-single.ps1 -Full for detailed help." -ForegroundColor Yellow
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

 if (-not $SkipInstall) {
  Ensure-DatrixPackagesInstalled
 }

 # Get Python executable from venv
 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"

 # Build arguments for Python script
 $pythonArgs = @($pythonScript)
 if ($TestPath) { $pythonArgs += $TestPath }
 if ($Project) { $pythonArgs += "--project"; $pythonArgs += $Project }
 if ($Keyword) { $pythonArgs += "--keyword"; $pythonArgs += $Keyword }
 if ($Marker) { $pythonArgs += "--marker"; $pythonArgs += $Marker }
 if ($VerboseOutput) { $pythonArgs += "--verbose" }
 if ($FailFast) { $pythonArgs += "--fail-fast" }
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
