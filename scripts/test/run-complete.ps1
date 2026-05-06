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
 Run complete workflow for everything except foundation (all examples in all minus foundation). Implies -All with test set non-tutorial.

.PARAMETER Domains
 Run complete workflow for domain examples only (examples/02-domains). Implies -All with test set domains.

.PARAMETER Language
 Target language for output path derivation (required). Options: python, typescript.
 The actual language used for generation is read from config/system-config.yaml.
 Can be abbreviated as -L.

.PARAMETER Platform
 Target platform for output path derivation (default: docker).
 The actual platform used for generation is read from config/system-config.yaml.
 Can be abbreviated as -P.

.PARAMETER TestSet
 Run complete workflow for a specific test set by name (default: all).
 E.g. tutorial01-10, tutorial11-20, tutorial21-30, tutorial31-43.
 See scripts/config/test-projects.json for available test sets. Implies batch mode when not "all".

.PARAMETER Rerun
 Re-run only projects whose previous test results had errors/failures, or projects that have never been tested.
 Scans .test_results in each project's output directory and includes the project if the latest result is not PASSED.
 When a project needs re-running, regeneration (Step 2) also happens unless -Skip2 is specified.
 Combines with -TestSet, -Tutorial, -NonTutorial, -Domains to control which project set is checked.

.PARAMETER SkipVenv
 Skip virtual environment activation (use current Python environment).

.PARAMETER Skip1
 Skip Step 1 (syntax checker).

.PARAMETER Skip2
 Skip Step 2 (code generation).

.PARAMETER Skip3
 Skip Step 3 (unit tests for generated projects).

.PARAMETER Skip4
 Skip Step 4 (spec tests for generated projects).

.PARAMETER Skip5
 Skip Step 5 (deployment/integration tests for generated projects).

.PARAMETER FreshBuild
 Force fresh Docker builds (--no-cache) for deployment tests. By default, deploy tests use Docker layer cache for faster builds.

.PARAMETER SkipInstall
 Skip pip/network installs during generation (sets DATRIX_OFFLINE for the workflow). Requires a fully populated .venv.

.PARAMETER DebugLogging
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER Dbg
 Alias for -DebugLogging. Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\run-complete.ps1 "examples/01-tutorial/01-basic-entity/system.dtrx" -L python
 Runs the complete workflow; output path is derived by run_complete.py from test-projects.json (e.g. .generated/python/docker/01-tutorial/01-basic-entity).

.EXAMPLE
 .\run-complete.ps1 "examples/01-tutorial/01-basic-entity/system.dtrx" ".generated/python/docker/01-tutorial/01-basic-entity" -L python
 Runs the complete workflow with explicit output path.

.EXAMPLE
 .\run-complete.ps1 "examples/01-tutorial/01-basic-entity/system.dtrx" ".generated/python/docker/01-tutorial/01-basic-entity" -Language python -Platform docker
 Runs with explicit language and platform.

.EXAMPLE
 .\run-complete.ps1 -All -L python
 Runs the complete workflow for all examples (Python).

.EXAMPLE
 .\run-complete.ps1 -Tutorial -L python
 Runs the complete workflow for tutorial examples only (01-tutorial folder, Python).

.EXAMPLE
 .\run-complete.ps1 -NonTutorial -L typescript
 Runs the complete workflow for everything except tutorial (TypeScript).

.EXAMPLE
 .\run-complete.ps1 -Domains -L python
 Runs the complete workflow for domain examples only (02-domains folder, Python).

.EXAMPLE
 .\run-complete.ps1 -TestSet tutorial01-10 -L python
 Runs the complete workflow for the tutorial01-10 test set (tutorials 01-10, Python).

.EXAMPLE
 .\run-complete.ps1 -L python -Skip1
 Skips Step 1 (syntax checker).

.EXAMPLE
 .\run-complete.ps1 -L python -Skip3 -Skip4 -Skip5
 Runs only Steps 1-2, skipping unit, spec, and deployment tests for generated projects.

.EXAMPLE
 .\run-complete.ps1 -Tutorial -L python -FreshBuild
 Runs tutorial examples with fresh Docker builds (--no-cache, no layer cache) for maximum validation confidence.

.EXAMPLE
 .\run-complete.ps1 -Rerun -L python
 Re-runs only projects that previously failed or have never been tested (all test set).

.EXAMPLE
 .\run-complete.ps1 -Rerun -Domains -L python
 Re-runs only failed/untested domain projects.

.EXAMPLE
 .\run-complete.ps1 -Rerun -L python -Skip2
 Re-runs failed/untested projects without regenerating code (tests only).

.EXAMPLE
 $env:DATRIX_OFFLINE = "1"; .\run-complete.ps1 -Tutorial -L python
 Offline: no pip during the workflow (requires a ready .venv). Or use -SkipInstall (sets DATRIX_OFFLINE for the Python driver).
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
 [ValidateSet("python", "typescript")]
 [string]$Language,

 [Parameter()]
 [Alias("P")]
 [ValidateSet("docker", "kubernetes", "k8s")]
 [string]$Platform = "docker",

 [Parameter()]
 [Alias("H")]
 [string]$Hosting = "",

 [Parameter()]
 [string]$TestSet = "all",

 [switch]$Rerun,

 [switch]$SkipVenv,
 [switch]$Skip1,
 [switch]$Skip2,
 [switch]$Skip3,
 [switch]$Skip4,
 [switch]$Skip5,
 [switch]$FreshBuild,
 [switch]$SkipInstall,
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

# Validate mandatory -Language parameter (not using [Parameter(Mandatory)] to avoid interactive prompt)
if ([string]::IsNullOrWhiteSpace($Language)) {
 Write-ErrorMsg "Error: -Language (-L) parameter is required. Options: python, typescript."
 Write-ErrorMsg "Usage: .\run-complete.ps1 <ExamplePath> [OutputPath] -Language <lang> [-Platform <platform>]"
 Write-ErrorMsg "   Or: .\run-complete.ps1 -All | -Tutorial | -NonTutorial | -Domains | -TestSet <set> -Language <lang>"
 exit 1
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
$batchMode = $All -or $Tutorial -or $NonTutorial -or $Domains -or ($TestSet -ne "all") -or $Rerun
if (-not $batchMode) {
 if ([string]::IsNullOrWhiteSpace($ExamplePath)) {
  Write-ErrorMsg "Error: ExamplePath is required when no batch switch (-All, -Tutorial, -NonTutorial, -Domains, -TestSet, -Rerun) is specified."
  Write-ErrorMsg "Usage: .\run-complete.ps1 <ExamplePath> [OutputPath] -Language <lang> [-Platform <platform>]"
  Write-ErrorMsg " Or: .\run-complete.ps1 -All | -Tutorial | -NonTutorial | -Domains | -TestSet <set> | -Rerun -Language <lang>"
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

# --- Rerun mode: scan .test_results, filter to failed/missing, run each project individually ---
if ($Rerun) {
 try {
 # Determine which test set to scan
 $testSetName = if ($Tutorial) { "tutorial-all" }
 elseif ($NonTutorial) { "non-tutorial" }
 elseif ($Domains) { "domains" }
 elseif ($TestSet -ne "all") { $TestSet }
 else { "all" }

 # Load test-projects.json
 $configPath = Join-Path $datrixRoot "datrix\scripts\config\test-projects.json"
 $config = Get-Content $configPath -Raw | ConvertFrom-Json

 # Build flat lookup of all projects by name
 $allProjectsDict = @{}
 foreach ($category in $config.projects.PSObject.Properties) {
  foreach ($proj in $category.Value) {
   $allProjectsDict[$proj.name] = $proj
  }
 }

 # Resolve project names from test set
 $projectNames = @()
 if ($config.testSets.PSObject.Properties[$testSetName]) {
  $projectNames = @($config.testSets.$testSetName)
 } elseif ($testSetName -eq "tutorial-all") {
  # Legacy: foundation projects
  foreach ($category in $config.projects.PSObject.Properties) {
   foreach ($proj in $category.Value) {
    $normalizedPath = $proj.path -replace '\\', '/'
    if ($normalizedPath.StartsWith("examples/01-foundation/")) {
     $projectNames += $proj.name
    }
   }
  }
 } elseif ($testSetName -eq "non-tutorial") {
  $allNames = @($config.testSets.all)
  $foundationNames = @()
  foreach ($category in $config.projects.PSObject.Properties) {
   foreach ($proj in $category.Value) {
    $normalizedPath = $proj.path -replace '\\', '/'
    if ($normalizedPath.StartsWith("examples/01-foundation/")) {
     $foundationNames += $proj.name
    }
   }
  }
  $projectNames = $allNames | Where-Object { $_ -notin $foundationNames }
 } else {
  Write-ErrorMsg "Error: Test set '$testSetName' not found in test-projects.json."
  Write-ErrorMsg "Available: $($config.testSets.PSObject.Properties.Name -join ', ')"
  Invoke-Cleanup
  exit 1
 }

 # For each project, compute output path and check .test_results
 $generatedBase = Join-Path $datrixRoot ".generated"
 $projectsToRerun = @()

 foreach ($projName in $projectNames) {
  if (-not $allProjectsDict.ContainsKey($projName)) { continue }
  $proj = $allProjectsDict[$projName]

  # Build output path: remove "examples/" prefix, remove "/system.dtrx" suffix, prepend language/platform
  $sourcePath = ($proj.path -replace '\\', '/')
  $relative = $sourcePath -replace '^examples/', ''
  if ($relative -match '/system\.dtrx$') {
   $base = $relative -replace '/system\.dtrx$', ''
  } elseif ($relative -match '\.dtrx$') {
   $base = $relative -replace '\.dtrx$', ''
  } else {
   $base = $relative
  }
  $outputRelative = "$Language/$Platform/$base"
  $projectOutputDir = Join-Path $generatedBase $outputRelative

  # Check .test_results for latest result of each test type (unit-tests, deploy-test)
  # A project needs re-run if ANY test type is missing or not PASSED.
  $needsRerun = $false
  $testResultsDir = Join-Path $projectOutputDir ".test_results"

  if (-not (Test-Path $testResultsDir)) {
   # No test results at all — needs rerun
   $needsRerun = $true
  } else {
   # Check unit-tests: use index.json (reliable for unit tests)
   $unitDirs = @(Get-ChildItem -Path $testResultsDir -Directory -ErrorAction SilentlyContinue |
    Where-Object { $_.Name -like "unit-tests-*" })
   if ($unitDirs.Count -eq 0) {
    $needsRerun = $true
   } else {
    $unitIndexFiles = @()
    foreach ($dir in $unitDirs) {
     $idx = Join-Path $dir.FullName "index.json"
     if (Test-Path $idx) { $unitIndexFiles += Get-Item $idx }
    }
    if ($unitIndexFiles.Count -eq 0) {
     $needsRerun = $true
    } else {
     $latestUnitIndex = $unitIndexFiles | Sort-Object LastWriteTime -Descending | Select-Object -First 1
     $unitResult = Get-Content $latestUnitIndex.FullName -Raw | ConvertFrom-Json
     if ($unitResult.result -ne "PASSED") { $needsRerun = $true }
    }
   }

   # Check deploy-test: use failures.json (index.json is unreliable for deploy tests)
   if (-not $needsRerun) {
    $deployDirs = @(Get-ChildItem -Path $testResultsDir -Directory -ErrorAction SilentlyContinue |
     Where-Object { $_.Name -like "deploy-test-*" })
    if ($deployDirs.Count -eq 0) {
     $needsRerun = $true
    } else {
     # Find the most recent deploy-test dir by timestamp in name (YYYYMMDD-HHMMSS)
     $latestDeployDir = $deployDirs | Sort-Object Name -Descending | Select-Object -First 1
     $failuresFile = Join-Path $latestDeployDir.FullName "failures.json"
     if (-not (Test-Path $failuresFile)) {
      # No failures.json means test didn't complete — needs rerun
      $needsRerun = $true
     } else {
      $failures = Get-Content $failuresFile -Raw | ConvertFrom-Json
      if ($failures.summary.total -gt 0) { $needsRerun = $true }
     }
    }
   }
  }

  if ($needsRerun) {
   $projectsToRerun += @{
    Name = $projName
    ExamplePath = (Join-Path (Join-Path $datrixRoot "datrix") $sourcePath)
    OutputPath = $projectOutputDir
   }
  }
 }

 if ($projectsToRerun.Count -eq 0) {
  Write-Success "All projects in test set '$testSetName' have passing results. Nothing to re-run."
  Invoke-Cleanup
  exit 0
 }

 Write-Info "Rerun mode: $($projectsToRerun.Count) of $($projectNames.Count) projects need re-running:"
 foreach ($p in $projectsToRerun) {
  Write-Info "  - $($p.Name)"
 }
 Write-Info ""

 # Set environment variable for fresh build mode
 if ($FreshBuild) {
  $env:DEPLOY_TEST_FRESH_BUILD = "true"
  Write-Info "Fresh build mode enabled (deploy tests will use --no-cache)"
 }

 # Run each project individually via run_complete.py in single-example mode
 $rerunSuccess = 0
 $rerunFail = 0
 $rerunExitCode = 0

 for ($i = 0; $i -lt $projectsToRerun.Count; $i++) {
  $p = $projectsToRerun[$i]
  Write-Info ""
  Write-Info "=========================================="
  Write-Info "[$($i+1)/$($projectsToRerun.Count)] Re-running: $($p.Name)"
  Write-Info "=========================================="

  $singleArgs = @($runCompleteScript)
  $singleArgs += $p.ExamplePath
  $singleArgs += $p.OutputPath
  $singleArgs += "-Language"
  $singleArgs += $Language
  $singleArgs += "-Platform"
  $singleArgs += $Platform
  if ($Skip1) { $singleArgs += "-Skip1" }
  if ($Skip2) { $singleArgs += "-Skip2" }
  if ($Skip3) { $singleArgs += "-Skip3" }
  if ($Skip4) { $singleArgs += "-Skip4" }
  if ($Skip5) { $singleArgs += "-Skip5" }
  if (-not [string]::IsNullOrWhiteSpace($Hosting)) {
   $singleArgs += "-Hosting"
   $singleArgs += $Hosting
  }
  if ($DebugLogging) { $singleArgs += "--debug" }
  if ($SkipInstall) { $singleArgs += "--skip-install" }

  Write-Info "Running: $pythonExe -u $($singleArgs -join ' ')"
  Write-Info ""

  & $pythonExe -u @singleArgs
  $projectExitCode = $LASTEXITCODE

  if ($projectExitCode -eq 130) {
   Write-Warning "Interrupted by user during: $($p.Name)"
   $rerunExitCode = 130
   break
  } elseif ($projectExitCode -eq 0) {
   Write-Success " [OK] $($p.Name)"
   $rerunSuccess++
  } else {
   Write-ErrorMsg " [FAILED] $($p.Name) (exit code: $projectExitCode)"
   $rerunFail++
   $rerunExitCode = 1
  }
 }

 # Final summary
 Write-Info ""
 Write-Info "=========================================="
 Write-Info "Rerun Summary"
 Write-Info "=========================================="
 Write-Info "Projects re-run: $($rerunSuccess + $rerunFail) / $($projectsToRerun.Count)"
 if ($rerunSuccess -gt 0) { Write-Success "  Passed: $rerunSuccess" }
 if ($rerunFail -gt 0) { Write-ErrorMsg "  Failed: $rerunFail" }
 Write-Info "=========================================="

 Invoke-Cleanup
 exit $rerunExitCode

 } catch {
  Write-ErrorMsg "Error in rerun mode: $($_.Exception.Message)"
  Write-ErrorMsg "At: $($_.InvocationInfo.ScriptLineNumber): $($_.InvocationInfo.Line.Trim())"
  Invoke-Cleanup
  exit 1
 }
}

# Build arguments for run_complete.py
$pythonArgs = @($runCompleteScript)
if ($batchMode) {
 $pythonArgs += "-All"
 $testSetName = if ($Tutorial) { "tutorial-all" }
 elseif ($NonTutorial) { "non-tutorial" }
 elseif ($Domains) { "domains" }
 else { $TestSet }
 if ($testSetName -ne "all") {
 $pythonArgs += "--test-set"
 $pythonArgs += $testSetName
 }
 $pythonArgs += "-Language"
 $pythonArgs += $Language
 if ($Platform) {
 $pythonArgs += "-Platform"
 $pythonArgs += $Platform
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
 # Add parameters
 $pythonArgs += "-Language"
 $pythonArgs += $Language
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
if ($Skip3) {
 $pythonArgs += "-Skip3"
}
if ($Skip4) {
 $pythonArgs += "-Skip4"
}
if ($Skip5) {
 $pythonArgs += "-Skip5"
}
if (-not [string]::IsNullOrWhiteSpace($Hosting)) {
 $pythonArgs += "-Hosting"
 $pythonArgs += $Hosting
}
if ($DebugLogging) {
 $pythonArgs += "--debug"
}
if ($SkipInstall) {
 $pythonArgs += "--skip-install"
}

# Set environment variable for fresh build mode (deploy tests will use --no-cache)
if ($FreshBuild) {
 $env:DEPLOY_TEST_FRESH_BUILD = "true"
 Write-Info "Fresh build mode enabled (deploy tests will use --no-cache)"
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
