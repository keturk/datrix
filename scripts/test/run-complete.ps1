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
 Output directory path for the generated project. When omitted, run_complete.py derives it from scripts/config/test-projects.json (defaultLanguage), the -Platform runtime, the example path, and the provider read from the example's config/system.dcfg.

.PARAMETER All
 Run all examples instead of a single example.

.PARAMETER Domains
 Run complete workflow for domain examples only (examples/02-domains). Implies -All with test set domains.

.PARAMETER Language
 Target generation language (required). Accepts any registered datrix.languages
 target, validated at runtime against the installed set (never a hardcoded
 python/typescript list). Threaded through generate.ps1 to
 `datrix generate --language` as the real generation target -- it also selects
 the output-path language segment, so the two can never disagree.
 Can be abbreviated as -L.

.PARAMETER Platform
 Target runtime for output path derivation (default: docker-compose).
 The provider segment of the output path is read from each project's config/system.dcfg
 deployment block for the active profile -- it is NOT specified here. A legacy
 "runtime/provider" value is accepted; only the runtime half is used.
 Can be abbreviated as -P.

.PARAMETER TestSet
 Run complete workflow for a specific test set by name (default: all).
 See scripts/config/test-projects.json for available test sets. Implies batch mode when not "all".

.PARAMETER Rerun
 Re-run only projects whose previous test results had errors/failures, or projects that have never been tested.
 Scans .test_results in each project's output directory and includes the project if the latest result is not PASSED.
 When a project needs re-running, regeneration (Step 2) also happens unless -Skip2 is specified.
 Combines with -TestSet, -Domains to control which project set is checked.

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

.PARAMETER VerboseOutput
 Enable verbose output. When not specified, minimal output is shown (summary only).

.PARAMETER FreshBuild
 Force fresh Docker builds (--no-cache) for deployment tests. By default, deploy tests use Docker layer cache for faster builds.

.PARAMETER DebugLogging
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER Dbg
 Alias for -DebugLogging. Enable debug logging (DEBUG level instead of INFO).

.PARAMETER LlmSummary
 Print advisory local LLM post-run summary from aggregate indexes.

.PARAMETER LlmLimit
 Maximum clusters/projects per aggregate index for advisory LLM summary. Default: 12.

.PARAMETER LocalMachines
 Machines to search for local model servers, in preference order. Omit to search the
 default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
 Models to use for advisory summary, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
 Request timeout in seconds for advisory summary.

.PARAMETER LlmNumPredict
 Max generated tokens for advisory summary.

.PARAMETER LlmTemperature
 Sampling temperature for advisory summary.

.EXAMPLE
 .\run-complete.ps1 "examples/02-features/01-core-data-modeling/entities/system.dtrx" -L python
 Runs the complete workflow; output path is derived by run_complete.py from test-projects.json.

.EXAMPLE
 .\run-complete.ps1 "examples/02-features/01-core-data-modeling/entities/system.dtrx" ".generated/python/docker-compose/local/02-features/01-core-data-modeling/entities" -L python
 Runs the complete workflow with explicit output path.

.EXAMPLE
 .\run-complete.ps1 -All -L python
 Runs the complete workflow for all examples (Python).

.EXAMPLE
 .\run-complete.ps1 -Domains -L python
 Runs the complete workflow for domain examples only (02-domains folder, Python).

.EXAMPLE
 .\run-complete.ps1 -TestSet foundation -L python
 Runs the complete workflow for the foundation test set (Python).

.EXAMPLE
 .\run-complete.ps1 -L python -Skip1
 Skips Step 1 (syntax checker).

.EXAMPLE
 .\run-complete.ps1 -L python -Skip3 -Skip4 -Skip5
 Runs only Steps 1-2, skipping unit, spec, and deployment tests for generated projects.

.EXAMPLE
 .\run-complete.ps1 -TestSet foundation -L python -FreshBuild
 Runs foundation examples with fresh Docker builds (--no-cache, no layer cache) for maximum validation confidence.

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
 $env:DATRIX_OFFLINE = "1"; .\run-complete.ps1 -TestSet foundation -L python
 Offline: no pip during the workflow (requires a ready .venv).
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$ExamplePath,

 [Parameter(Position=1)]
 [string]$OutputPath,

 [switch]$All,

 [switch]$Domains,

 [Parameter()]
 [Alias("L")]
 [string]$Language,

 [Parameter()]
 [Alias("P")]
 [string]$Platform = "docker-compose",

 [Parameter()]
 [Alias("H")]
 [string]$Hosting = "",

 [Parameter()]
 [string]$TestSet = "all",

 [switch]$Rerun,

 [switch]$VerboseOutput,
 [switch]$Skip1,
 [switch]$Skip2,
 [switch]$Skip3,
 [switch]$Skip4,
 [switch]$Skip5,
 [switch]$FreshBuild,
 [Alias("Dbg")]
 [switch]$DebugLogging,
 [switch]$LlmSummary,
 [int]$LlmLimit = 12,
 [string[]]$LocalMachines = @(),
 [string[]]$LlmModel = @(),
 [int]$LlmTimeout = 180,
 [int]$LlmNumPredict = 4096,
 [double]$LlmTemperature = 0.1
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

# Validate mandatory -Language parameter (not using [Parameter(Mandatory)] to avoid interactive prompt).
# The value is validated against the installed datrix.languages set below, once
# the venv python is resolved -- not a static ValidateSet -- so a newly installed
# datrix-codegen-<lang> package is selectable here with no edit to this script.
if ([string]::IsNullOrWhiteSpace($Language)) {
 Write-ErrorMsg "Error: -Language (-L) parameter is required (any registered datrix.languages target)."
 Write-ErrorMsg "Usage: .\run-complete.ps1 <ExamplePath> [OutputPath] -Language <lang> [-Platform <platform>]"
 Write-ErrorMsg "   Or: .\run-complete.ps1 -All | -Domains | -TestSet <set> -Language <lang>"
 exit 1
}

# -Platform now carries only the runtime segment; the provider segment of the
# output path comes from each project's config/system.dcfg. Accept a legacy
# "runtime/provider" value by keeping only the runtime half.
$Platform = $Platform.Split('/')[0]

# Script setup
$ErrorActionPreference = "Stop"
$runCompleteScript = Join-Path $PSScriptRoot "lib\run_complete.py"
$commonDir = Join-Path $PSScriptRoot "..\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $commonDir "DatrixPythonScript.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixWorkspaceRoot = Get-DatrixWorkspaceRoot

# Unbuffered child output (python -u), so each step's lines appear as they are written.
$env:PYTHONUNBUFFERED = "1"

# Validate parameters
$batchMode = $All -or $Domains -or ($TestSet -ne "all") -or $Rerun
if (-not $batchMode) {
 if ([string]::IsNullOrWhiteSpace($ExamplePath)) {
  Write-ErrorMsg "Error: ExamplePath is required when no batch switch (-All, -Domains, -TestSet, -Rerun) is specified."
  Write-ErrorMsg "Usage: .\run-complete.ps1 <ExamplePath> [OutputPath] -Language <lang> [-Platform <platform>]"
  Write-ErrorMsg " Or: .\run-complete.ps1 -All | -Domains | -TestSet <set> | -Rerun -Language <lang>"
  exit 1
 }
 # When OutputPath is omitted, run_complete.py derives it from test-projects.json (defaultLanguage),
 # the -Platform runtime, and the provider read from the example's config/system.dcfg.
}

Write-Info "=========================================="
Write-Info "Datrix Complete Workflow Runner"
Write-Info "=========================================="
Write-Info ""

# Validate -Language against the installed datrix.languages set (runtime discovery,
# never a hardcoded python/typescript literal) so a newly installed
# datrix-codegen-<lang> package is accepted with no edit to this script.
$installedLanguages = Get-DatrixInstalledLanguages -PythonExe (Join-Path (Get-DatrixVenvPath) "Scripts\python.exe")
if ($Language -notin $installedLanguages) {
 Write-ErrorMsg "Error: language '$Language' is not an installed datrix.languages target."
 Write-ErrorMsg "Installed languages: $($installedLanguages -join ', ')."
 Write-ErrorMsg "Install the corresponding datrix-codegen-<language> package to add it."
 exit 1
}

# --- Rerun mode: scan .test_results, filter to failed/missing, run each project individually ---
if ($Rerun) {
 try {
 # Determine which test set to scan
 $testSetName = if ($Domains) { "domains" }
 elseif ($TestSet -ne "all") { $TestSet }
 else { "all" }

 # Load test-projects.json
 $configPath = Join-Path $datrixWorkspaceRoot "datrix\scripts\config\test-projects.json"
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
 } else {
  Write-ErrorMsg "Error: Test set '$testSetName' not found in test-projects.json."
  Write-ErrorMsg "Available: $($config.testSets.PSObject.Properties.Name -join ', ')"
  exit 1
 }

 # For each project, compute output path and check .test_results
 # Honor skip flags in rerun selection: skipped test types are not inspected.
 $checkUnitResults = -not $Skip3
 $checkDeployResults = -not $Skip4
 if (-not $checkUnitResults -and -not $checkDeployResults) {
  Write-Warning "Rerun mode: both Step 3 and Step 4 are skipped; no test-result folders will be inspected."
 }
 $generatedBase = Join-Path $datrixWorkspaceRoot ".generated"
 $projectsToRerun = @()

 foreach ($projName in $projectNames) {
  if (-not $allProjectsDict.ContainsKey($projName)) { continue }
  $proj = $allProjectsDict[$projName]

  # Build output path: remove "examples/" prefix, remove "/system.dtrx" suffix.
  $sourcePath = ($proj.path -replace '\\', '/')
  $relative = $sourcePath -replace '^examples/', ''
  if ($relative -match '/system\.dtrx$') {
   $base = $relative -replace '/system\.dtrx$', ''
  } elseif ($relative -match '\.dtrx$') {
   $base = $relative -replace '\.dtrx$', ''
  } else {
   $base = $relative
  }
  # Layout is {language}/{runtime}/{provider}/{base}. The provider segment is set
  # by each project's config/system.dcfg at generation time, so discover it on
  # disk rather than assuming a value.
  $runtimeDir = Join-Path $generatedBase (Join-Path $Language $Platform)
  $projectOutputDir = $null
  if (Test-Path $runtimeDir) {
   $projectOutputDir = Get-ChildItem -Path $runtimeDir -Directory -ErrorAction SilentlyContinue |
    ForEach-Object { Join-Path $_.FullName $base } |
    Where-Object { Test-Path $_ } |
    Select-Object -First 1
  }
  if (-not $projectOutputDir) {
   # Nothing generated yet — fall back to the default 'local' provider layout.
   $projectOutputDir = Join-Path $generatedBase "$Language/$Platform/local/$base"
  }

  # Check .test_results for latest result of each enabled test type (unit-tests, deploy-test)
  # A project needs re-run if ANY enabled test type is missing or not PASSED.
  $needsRerun = $false
  $testResultsDir = Join-Path $projectOutputDir ".test_results"

  if (-not (Test-Path $testResultsDir)) {
   # No test results at all — needs rerun only if at least one test type is enabled
   $needsRerun = $checkUnitResults -or $checkDeployResults
  } else {
   # Check unit-tests only when Step 3 is enabled.
   if ($checkUnitResults) {
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
   }

   # Check deploy-test only when Step 4 is enabled.
   if ($checkDeployResults -and -not $needsRerun) {
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
    ExamplePath = (Join-Path (Join-Path $datrixWorkspaceRoot "datrix") $sourcePath)
    OutputPath = $projectOutputDir
   }
  }
 }

 if ($projectsToRerun.Count -eq 0) {
  Write-Success "All projects in test set '$testSetName' have passing results. Nothing to re-run."
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

  $singleArgs = @()
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
  if ($VerboseOutput) { $singleArgs += "--verbose" }
  if ($LlmSummary) {
   $singleArgs += @(
    "--llm-summary",
    "--llm-limit", $LlmLimit,
    "--llm-num-predict", $LlmNumPredict,
    "--llm-temperature", $LlmTemperature
   )
   $singleArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
  }

  Write-Info "Running: run_complete.py $($singleArgs -join ' ')"
  Write-Info ""

  $projectExitCode = Invoke-DatrixPythonScript -Script $runCompleteScript -Arguments $singleArgs

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

 exit $rerunExitCode

 } catch {
  Write-ErrorMsg "Error in rerun mode: $($_.Exception.Message)"
  Write-ErrorMsg "At: $($_.InvocationInfo.ScriptLineNumber): $($_.InvocationInfo.Line.Trim())"
  exit 1
 }
}

# Build arguments for run_complete.py
$pythonArgs = @()
if ($batchMode) {
 $pythonArgs += "-All"
 $testSetName = if ($Domains) { "domains" }
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
if ($VerboseOutput) {
 $pythonArgs += "--verbose"
}
if ($LlmSummary) {
 $pythonArgs += @(
  "--llm-summary",
  "--llm-limit", $LlmLimit,
  "--llm-num-predict", $LlmNumPredict,
  "--llm-temperature", $LlmTemperature
 )
 $pythonArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
}

# Set environment variable for fresh build mode (deploy tests will use --no-cache)
if ($FreshBuild) {
 $env:DEPLOY_TEST_FRESH_BUILD = "true"
 Write-Info "Fresh build mode enabled (deploy tests will use --no-cache)"
}

# Display what we're about to run
Write-Info "Running: run_complete.py $($pythonArgs -join ' ')"
Write-Info ""
Write-Info "=========================================="
Write-Info ""

# Ctrl-C reaches the Python process, whose own signal handlers clean up its subprocesses
# and exit 130; the runner deactivates the venv on the way out.
$exitCode = Invoke-DatrixPythonScript -Script $runCompleteScript -Arguments $pythonArgs

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
