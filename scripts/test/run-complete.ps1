#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Complete Workflow Runner for Datrix - PowerShell Wrapper

.DESCRIPTION
 This script activates the virtual environment and runs the complete workflow
 that includes syntax checking, code generation, testing, and validation.

.PARAMETER ExamplePath
 Path to the .dtrx file to generate (required when -All is not specified).

.PARAMETER OutputPath
 Output directory path for the generated project. When omitted, run_complete.py derives it from scripts/config/test-projects.json (defaultLanguage, defaultPlatform) and the example path.

.PARAMETER All
 Run all examples instead of a single example.

.PARAMETER Tutorial
 Run complete workflow for tutorial examples only (examples/01-tutorial). Implies -All with test set tutorial-all.

.PARAMETER NonTutorial
 Run complete workflow for everything except tutorial (all examples in generate-all minus 01-tutorial). Implies -All with test set non-tutorial.

.PARAMETER Domains
 Run complete workflow for domain examples only (examples/02-domains). Implies -All with test set domains.

.PARAMETER Language
 Target language for output path derivation (default: python). Options: python, typescript.
 The actual language used for generation is read from config/system-config.yaml.
 Can be abbreviated as -L.

.PARAMETER Platform
 Target platform for output path derivation (default: docker).
 The actual platform used for generation is read from config/system-config.yaml.
 Can be abbreviated as -P.

.PARAMETER TestSet
 Run complete workflow for a specific test set by name (default: generate-all).
 E.g. tutorial01-10, tutorial11-20, tutorial21-30, tutorial31-41.
 See scripts/config/test-projects.json for available test sets. Implies batch mode when not "generate-all".

.PARAMETER SkipVenv
 Skip virtual environment activation (use current Python environment).

.PARAMETER Skip1
 Skip Step 1 (syntax checker).

.PARAMETER Skip2
 Skip Step 2 (code generation).

.PARAMETER Skip4
 Skip Step 4 (unit tests for generated projects).

.PARAMETER Skip5
 Skip Step 5 (deployment/integration tests for generated projects).

.PARAMETER DebugLogging
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER Dbg
 Alias for -DebugLogging. Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\run-complete.ps1 "examples/01-tutorial/01-basic-entity/system.dtrx"
 Runs the complete workflow; output path is derived by run_complete.py from test-projects.json (e.g. .generated/python/docker/01-tutorial/01-basic-entity).

.EXAMPLE
 .\run-complete.ps1 "examples/01-tutorial/01-basic-entity/system.dtrx" ".generated/python/docker/01-tutorial/01-basic-entity"
 Runs the complete workflow with explicit output path.

.EXAMPLE
 .\run-complete.ps1 "examples/01-tutorial/01-basic-entity/system.dtrx" ".generated/python/docker/01-tutorial/01-basic-entity" -Language python -Platform docker
 Runs with custom language and platform.

.EXAMPLE
 .\run-complete.ps1 -All
 Runs the complete workflow for all examples.

.EXAMPLE
 .\run-complete.ps1 -Tutorial
 Runs the complete workflow for tutorial examples only (01-tutorial folder).

.EXAMPLE
 .\run-complete.ps1 -NonTutorial
 Runs the complete workflow for everything except tutorial (all examples minus 01-tutorial).

.EXAMPLE
 .\run-complete.ps1 -Domains
 Runs the complete workflow for domain examples only (02-domains folder).

.EXAMPLE
 .\run-complete.ps1 -TestSet tutorial01-10
 Runs the complete workflow for the tutorial01-10 test set (tutorials 01-10).

.EXAMPLE
 .\run-complete.ps1 -Skip1
 Skips Step 1 (syntax checker).

.EXAMPLE
 .\run-complete.ps1 -Skip4 -Skip5
 Runs only Steps 1-2, skipping unit and deployment tests for generated projects.
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$ExamplePath,

 [Parameter(Position=1)]
 [string]$OutputPath,

 [switch]$All,

 [switch]$Tutorial,

 [switch]$NonTutorial,

 [switch]$Domains,

 [Parameter()]
 [Alias("L")]
 [string]$Language = "python",

 [Parameter()]
 [Alias("P")]
 [string]$Platform = "docker",

 [Parameter()]
 [string]$TestSet = "generate-all",

 [switch]$SkipVenv,
 [switch]$Skip1,
 [switch]$Skip2,
 [switch]$Skip4,
 [switch]$Skip5,
 [Alias("Dbg")]
 [switch]$DebugLogging
)

# Color output functions
function Write-Success {
 param([string]$Message)
 Write-Host $Message -ForegroundColor Green
}

function Write-Info {
 param([string]$Message)
 Write-Host $Message -ForegroundColor Cyan
}

function Write-Warning {
 param([string]$Message)
 Write-Host $Message -ForegroundColor Yellow
}

function Write-ErrorMsg {
 param([string]$Message)
 Write-Host $Message -ForegroundColor Red
}

# Script setup
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runCompleteScript = Join-Path $libraryDir "test\run_complete.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Get datrix root
$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRoot

# Check if run_complete.py exists
if (-not (Test-Path $runCompleteScript)) {
 Write-ErrorMsg "Error: run_complete.py not found at: $runCompleteScript"
 exit 1
}

# Validate parameters
$batchMode = $All -or $Tutorial -or $NonTutorial -or $Domains -or ($TestSet -ne "generate-all")
if (-not $batchMode) {
 if ([string]::IsNullOrWhiteSpace($ExamplePath)) {
  Write-ErrorMsg "Error: ExamplePath is required when no batch switch (-All, -Tutorial, -NonTutorial, -Domains, -TestSet) is specified."
  Write-ErrorMsg "Usage: .\run-complete.ps1 <ExamplePath> [OutputPath] [-Language <lang>] [-Platform <platform>]"
  Write-ErrorMsg " Or: .\run-complete.ps1 -All | -Tutorial | -NonTutorial | -Domains | -TestSet <set>"
  exit 1
 }
 # When OutputPath is omitted, run_complete.py derives it from test-projects.json (defaultLanguage, defaultPlatform)
}

Write-Info "=========================================="
Write-Info "Datrix Complete Workflow Runner"
Write-Info "=========================================="
Write-Info ""

# Function to handle cleanup on exit
function Invoke-Cleanup {
 Disable-DatrixVenv
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

# Determine which virtual environment to use
$venvPath = $null
$pythonExe = "python"

if (-not $SkipVenv) {
 # Activate virtual environment (common venv at D:\datrix\.venv where all projects are installed in editable mode)
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
 Write-Host ""
 Write-ErrorMsg "ERROR: Failed to activate virtual environment!"
 Write-Host ""
 Write-Host "To create the Datrix common virtual environment, run:" -ForegroundColor Yellow
 Write-Host " cd $datrixRoot" -ForegroundColor Cyan
 Write-Host " python -m venv .venv" -ForegroundColor Cyan
 Write-Host " .\.venv\Scripts\Activate.ps1" -ForegroundColor Cyan
 Write-Host " # Then install all projects in editable mode" -ForegroundColor Cyan
 Write-Host ""
 exit 1
 }

 # Get Python executable from venv
 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"
} else {
 Write-Info "Using system Python (virtual environment not used)"
 Write-Info ""
}

# Display Python information
Write-Info "Python executable: $pythonExe"
$pythonVersion = & $pythonExe --version 2>&1
Write-Info "Python version: $pythonVersion"
Write-Info ""

# Build arguments for run_complete.py
$pythonArgs = @($runCompleteScript)
if ($batchMode) {
 $pythonArgs += "-All"
 $testSetName = if ($Tutorial) { "tutorial-all" }
 elseif ($NonTutorial) { "non-tutorial" }
 elseif ($Domains) { "domains" }
 else { $TestSet }
 if ($testSetName -ne "generate-all") {
 $pythonArgs += "--test-set"
 $pythonArgs += $testSetName
 }
} else {
 # Resolve paths to absolute paths before passing to Python
 # This ensures paths work correctly regardless of where Python script runs from
 $currentDir = Get-Location

 if ([System.IO.Path]::IsPathRooted($ExamplePath)) {
 $resolvedExamplePath = $ExamplePath
 } else {
 # Resolve relative to current directory
 try {
 $resolvedExamplePath = (Resolve-Path $ExamplePath -ErrorAction Stop).Path
 } catch {
 # If file doesn't exist yet, construct absolute path manually
 $resolvedExamplePath = [System.IO.Path]::GetFullPath((Join-Path $currentDir $ExamplePath))
 }
 }

 # Normalize path - remove trailing slashes/backslashes for consistency
 $resolvedExamplePath = $resolvedExamplePath.TrimEnd('\', '/')

 # Add example path; add output path only when explicitly provided (otherwise run_complete.py derives from test-projects.json)
 $pythonArgs += $resolvedExamplePath
 if (-not [string]::IsNullOrWhiteSpace($OutputPath)) {
  if ([System.IO.Path]::IsPathRooted($OutputPath)) {
   $resolvedOutputPath = $OutputPath
  } else {
   $resolvedOutputPath = [System.IO.Path]::GetFullPath((Join-Path $currentDir $OutputPath))
  }
  $resolvedOutputPath = $resolvedOutputPath.TrimEnd('\', '/')
  $pythonArgs += $resolvedOutputPath
 }
 # Add optional parameters
 if ($Language) {
 $pythonArgs += "-Language"
 $pythonArgs += $Language
 }
 if ($Platform) {
 $pythonArgs += "-Platform"
 $pythonArgs += $Platform
 }
}

# Add skip flags
if ($Skip1) {
 $pythonArgs += "-Skip1"
}
if ($Skip2) {
 $pythonArgs += "-Skip2"
}
if ($Skip4) {
 $pythonArgs += "-Skip4"
}
if ($Skip5) {
 $pythonArgs += "-Skip5"
}
if ($DebugLogging) {
 $pythonArgs += "--debug"
}

# Display what we're about to run
Write-Info "Running: $pythonExe -u $($pythonArgs -join ' ')"
Write-Info "Working directory: $datrixRoot"
Write-Info ""
Write-Info "=========================================="
Write-Info ""

# Trap Ctrl-C to ensure proper cleanup
# Note: PowerShell will pass Ctrl-C to the Python process, which has its own signal handlers
# This trap provides an additional safety layer
trap {
 Write-Host ""
 Write-Warning "Interrupted! The Python process should handle cleanup..."
 Invoke-Cleanup
 # Python signal handler will handle subprocess cleanup
 # Exit with code 130 (standard for SIGINT/Ctrl-C)
 exit 130
}

# Run the Python script from datrix root directory with unbuffered output (-u flag)
try {
 & $pythonExe -u @pythonArgs
 $exitCode = $LASTEXITCODE
} catch {
 # Handle interruption or other errors
 if ($_.Exception.Message -match "interrupt|cancel") {
 Write-Warning "Process was interrupted"
 $exitCode = 130
 } else {
 Write-ErrorMsg "Error running Python script: $($_.Exception.Message)"
 $exitCode = 1
 }
} finally {
 # Ensure virtual environment is deactivated even on Ctrl-C
 Invoke-Cleanup
}

Write-Info ""
Write-Info "=========================================="

# Exit with the same code as the Python script
if ($exitCode -eq 0) {
 Write-Success "Workflow completed successfully!"
 Write-Info "=========================================="
 exit 0
} elseif ($exitCode -eq 130) {
 Write-Warning "Workflow was interrupted by user (Ctrl-C)"
 Write-Info "=========================================="
 exit 130
} else {
 Write-ErrorMsg "Workflow failed with exit code: $exitCode"
 Write-Info "=========================================="
 exit $exitCode
}
