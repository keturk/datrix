#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run tests for Datrix projects using test_project.py.

.DESCRIPTION
 Activates the datrix virtual environment and runs test_project.py
 for one or more projects. Ensures virtual environment is deactivated even
 if the script is interrupted (Ctrl-C).

 By default, test output is minimal (summary + link to detailed results).
 Use -VerboseOutput to see full test output in the console.

.PARAMETER Projects
 One or more project names or folder paths to test (e.g., datrix-common, 
 .\datrix-common\, D:\datrix\datrix-common). Paths will be resolved and the 
 project name will be extracted from the folder name.

.PARAMETER All
 Run tests for all Datrix projects.

.PARAMETER Coverage
 Generate coverage reports.

.PARAMETER VerboseOutput
 Enable verbose test output. When not specified, minimal output is shown (summary only).

.PARAMETER NoSave
 Don't save test output to log files.

.PARAMETER NoAutoInstall
 Disable automatic dependency installation (prompt instead).

.PARAMETER Unit
 Run unit tests only.

.PARAMETER Integration
 Run integration tests only.

.PARAMETER E2E
 Run end-to-end tests only.

.PARAMETER Fast
 Run fast tests only (excludes slow tests).

.PARAMETER Slow
 Run slow tests only.

.PARAMETER Specific
 Run specific test file(s) or pattern. Several files/node-IDs may be given
 comma-separated in ONE invocation (e.g. "tests/unit/a.py,tests/unit/b.py") and
 run in a single pytest session. Commas inside parametrized node IDs ("[1,2]")
 are literal, not separators.

.PARAMETER Keyword
 Run tests matching keyword expression (-k option).

.PARAMETER Rerun
 Re-run tests only for projects whose latest timestamped test log reports a failure.
 Scans all projects, reads each project's .test_results directory, and runs tests
 only for those whose most recent run has failed or errored. Projects with no
 previous test results are skipped.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\test.ps1 -Rerun
 Re-run tests only for projects whose latest test log reports failures.

.EXAMPLE
 .\test.ps1 datrix-common
 Run tests for datrix-common only.

.EXAMPLE
 .\test.ps1 .\datrix-common\
 Run tests using folder path (project name extracted from path).

.EXAMPLE
 .\test.ps1 -All
 Run tests for all Datrix projects.

.EXAMPLE
 .\test.ps1 datrix-common datrix-language -Coverage
 Run tests for specific projects with coverage.

.EXAMPLE
 .\test.ps1 .\datrix-common\ .\datrix-language\ -Coverage
 Run tests for specific projects using folder paths with coverage.

.EXAMPLE
 .\test.ps1 datrix-common -Unit
 Run only unit tests for datrix-common.

.EXAMPLE
 .\test.ps1 -All -Fast
 Run fast tests for all projects (excludes slow tests).

.EXAMPLE
 .\test.ps1 datrix-common -Specific "tests/unit/test_parser.py"
 Run specific test file.

.EXAMPLE
 .\test.ps1 datrix-common -Specific "tests/unit/test_parser.py,tests/unit/test_types.py"
 Run several test files in one pytest session (one runner startup, one run directory).

.EXAMPLE
 .\test.ps1 datrix-language -Keyword "test_basic"
 Run tests matching keyword expression.

#>

[CmdletBinding()]
param(
 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$Projects,

 [switch]$All,
 [switch]$Rerun,
 [switch]$Coverage,
 [switch]$VerboseOutput,
 [switch]$NoSave,
 [switch]$NoAutoInstall,

 # Test type filters (mutually exclusive)
 [switch]$Unit,
 [switch]$Integration,
 [switch]$E2E,
 [switch]$Fast,
 [switch]$Slow,

 # Test selection
 [string]$Specific,
 [string]$Keyword,

 [Parameter()]
 [switch]$Dbg
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$testProjectScript = Join-Path $libraryDir "test\test_project.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Monorepo workspace root (Get-DatrixWorkspaceRootFromScript is exported from DatrixScriptCommon; nested DatrixPaths import is not visible here)
$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

# Check if test_project.py exists
if (-not (Test-Path $testProjectScript)) {
 Write-Error "Error: test_project.py not found at: $testProjectScript"
 exit 1
}

# Function to handle cleanup on exit
function Invoke-Cleanup {
 Disable-DatrixVenv
}

# Helper: determine whether a project's latest test run reported failures.
# Returns $true if latest run failed/errored, $false if it passed or has no results.
function Test-ProjectLatestRunFailed {
 param(
  [string]$ProjectName,
  [string]$DatrixRoot
 )

 $testResultsDir = Join-Path (Join-Path $DatrixRoot $ProjectName) ".test_results"
 if (-not (Test-Path $testResultsDir -PathType Container)) {
  return $false
 }

 # Prefer new directory format: test-results-YYYYMMDD-HHMMSS/
 $latestDir = Get-ChildItem -Path $testResultsDir -Directory -Filter "test-results-*" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

 if ($latestDir) {
  $indexJsonPath = Join-Path $latestDir.FullName "index.json"
  if (Test-Path $indexJsonPath) {
   try {
    $indexData = Get-Content $indexJsonPath -Raw | ConvertFrom-Json
    if ($indexData.result -eq "FAILED") { return $true }
    if (($indexData.counts.failed -gt 0) -or ($indexData.counts.error -gt 0)) { return $true }
    return $false
   } catch {
    # Fall through to full.log check
   }
  }
  # Fallback: parse full.log for failed count
  $fullLogPath = Join-Path $latestDir.FullName "full.log"
  if (Test-Path $fullLogPath) {
   $content = Get-Content $fullLogPath -Raw
   if ($content -match '\b\d+\s+failed\b') { return $true }
   return $false
  }
 }

 # Legacy: flat log files test-results-*.log
 $latestLog = Get-ChildItem -Path $testResultsDir -Filter "test-results-*.log" |
  Sort-Object LastWriteTime -Descending |
  Select-Object -First 1

 if ($latestLog) {
  $content = Get-Content $latestLog.FullName -Raw
  if ($content -match '\b\d+\s+failed\b' -or $content -match '\b\d+\s+error\b') { return $true }
  return $false
 }

 return $false
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

# Handle Ctrl-C with try-catch in the main execution
$originalAction = $ErrorActionPreference

# Main execution with proper error handling
try {
 # Determine which projects to test
 $projectsToTest = @()

 if ($All) {
  $projectsToTest = Get-DatrixTestablePackageNames -WorkspaceRoot $datrixWorkspaceRoot
  if ($projectsToTest.Count -eq 0) {
  Write-Host "ERROR: No Datrix projects found in: $datrixWorkspaceRoot" -ForegroundColor Red
  Write-Host ""
  Write-Host "Please ensure Datrix projects are located in the Datrix workspace root directory." -ForegroundColor Yellow
  exit 1
  }
  Write-Host "Running tests for all projects: $($projectsToTest -join ', ')" -ForegroundColor Cyan
 } elseif ($Rerun) {
  $allProjects = Get-DatrixTestablePackageNames -WorkspaceRoot $datrixWorkspaceRoot
  if ($allProjects.Count -eq 0) {
  Write-Host "ERROR: No Datrix projects found in: $datrixWorkspaceRoot" -ForegroundColor Red
  exit 1
  }
  Write-Host "Checking latest test results for all projects..." -ForegroundColor Cyan
  $projectsToTest = @()
  foreach ($p in $allProjects) {
  if (Test-ProjectLatestRunFailed -ProjectName $p -DatrixRoot $datrixRoot) {
   Write-Host "  [FAIL] $p - queued for re-run" -ForegroundColor Yellow
   $projectsToTest += $p
  } else {
   Write-Host "  [OK]   $p - latest run passed or no results, skipping" -ForegroundColor DarkGray
  }
  }
  if ($projectsToTest.Count -eq 0) {
  Write-Host ""
  Write-Host "No projects with failing latest test runs found. Nothing to re-run." -ForegroundColor Green
  exit 0
  }
  Write-Host ""
  Write-Host "Re-running tests for $($projectsToTest.Count) project(s): $($projectsToTest -join ', ')" -ForegroundColor Cyan
 } elseif ($Projects.Count -gt 0) {
 # Normalize project inputs (convert paths to project names if needed)
 $normalizedProjects = $Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }
 
 # Filter to only valid datrix projects
 $allProjects = Get-DatrixTestablePackageNames -WorkspaceRoot $datrixWorkspaceRoot
 $projectsToTest = $normalizedProjects | Where-Object { $allProjects -contains $_ }
 
 if ($projectsToTest.Count -eq 0) {
 Write-Host "ERROR: No valid projects specified." -ForegroundColor Red
 Write-Host ""
 Write-Host "Available projects:" -ForegroundColor Yellow
 foreach ($project in $allProjects) {
 Write-Host " - $project" -ForegroundColor Cyan
 }
 exit 1
 }
 Write-Host "Running tests for projects: $($projectsToTest -join ', ')" -ForegroundColor Cyan
 } else {
 Write-Host ""
 Write-Host "ERROR: No projects specified." -ForegroundColor Red
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host " .\test.ps1 <project-name> [options]" -ForegroundColor Cyan
  Write-Host " .\test.ps1 <folder-path> [options]" -ForegroundColor Cyan
  Write-Host " .\test.ps1 -All [options]" -ForegroundColor Cyan
  Write-Host " .\test.ps1 -Rerun [options]" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Examples:" -ForegroundColor Yellow
 Write-Host " .\test.ps1 datrix-common" -ForegroundColor Cyan
 Write-Host " .\test.ps1 .\datrix-common\" -ForegroundColor Cyan
 Write-Host " .\test.ps1 datrix-common datrix-language" -ForegroundColor Cyan
 Write-Host " .\test.ps1 .\datrix-common\ .\datrix-language\" -ForegroundColor Cyan
  Write-Host " .\test.ps1 -All" -ForegroundColor Cyan
  Write-Host " .\test.ps1 -Rerun" -ForegroundColor Cyan
  Write-Host " .\test.ps1 datrix-common -Coverage -VerboseOutput" -ForegroundColor Cyan
 Write-Host " .\test.ps1 datrix-common -Unit" -ForegroundColor Cyan
 Write-Host " .\test.ps1 -All -Fast" -ForegroundColor Cyan
 Write-Host " .\test.ps1 datrix-common -Specific `"tests/unit/test_parser.py`"" -ForegroundColor Cyan
 Write-Host " .\test.ps1 datrix-language -Keyword `"test_basic`"" -ForegroundColor Cyan
 Write-Host ""
 $availableProjects = Get-DatrixTestablePackageNames -WorkspaceRoot $datrixWorkspaceRoot
 if ($availableProjects.Count -gt 0) {
 Write-Host "Available projects:" -ForegroundColor Yellow
 foreach ($project in $availableProjects) {
 Write-Host " - $project" -ForegroundColor Cyan
 }
 Write-Host ""
 Write-Host "Total: $($availableProjects.Count) projects" -ForegroundColor Cyan
 } else {
 Write-Host "No projects found in: $datrixWorkspaceRoot" -ForegroundColor Yellow
 }
 Write-Host ""
 exit 1
 }

 # Activate virtual environment (common venv at D:\datrix\.venv where all projects are installed in editable mode)
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
 Write-Host ""
 Write-Host "ERROR: Failed to activate virtual environment!" -ForegroundColor Red
 Write-Host ""
 Write-Host "To create the Datrix common virtual environment, run:" -ForegroundColor Yellow
 Write-Host " cd $datrixWorkspaceRoot" -ForegroundColor Cyan
 Write-Host " python -m venv .venv" -ForegroundColor Cyan
 Write-Host " .\.venv\Scripts\Activate.ps1" -ForegroundColor Cyan
 Write-Host " # Then install all projects in editable mode" -ForegroundColor Cyan
 Write-Host ""
 Write-Error "ERROR: No virtual environment is currently active."
 exit 1
 }

 # Ensure all packages are installed once (before the project loop). Per-project Python must not reinstall.
 $packagesInstalled = Ensure-DatrixPackagesInstalled -SkipIfInstalled
 if (-not $packagesInstalled) {
 Write-Host ""
 Write-Host "ERROR: Failed to install or update packages!" -ForegroundColor Red
 Write-Host ""
 Write-Error "Failed to install or update packages"
 exit 1
 }
 # Signal to test_project.py that packages were ensured by caller; skip per-project pip install -e
 $env:DATRIX_PACKAGES_ENSURED = "1"

 # Validate mutually exclusive test type options
 $testTypeOptions = @($Unit, $Integration, $E2E, $Fast, $Slow)
 $testTypeCount = ($testTypeOptions | Where-Object { $_ }).Count
 if ($testTypeCount -gt 1) {
 Write-Host "ERROR: Only one test type option can be specified at a time." -ForegroundColor Red
 Write-Host "Choose one of: -Unit, -Integration, -E2E, -Fast, -Slow" -ForegroundColor Yellow
 exit 1
 }

 # Build base arguments for test_project.py
 $baseArgs = @()

 if ($Coverage) { $baseArgs += "--coverage" }
 if ($VerboseOutput) { $baseArgs += "--verbose" }
 if ($NoSave) { $baseArgs += "--no-save" }
 if ($NoAutoInstall) { $baseArgs += "--no-auto-install" }

 # Add test type filters
 if ($Unit) { $baseArgs += "--unit" }
 if ($Integration) { $baseArgs += "--integration" }
 if ($E2E) { $baseArgs += "--e2e" }
 if ($Fast) { $baseArgs += "--fast" }
 if ($Slow) { $baseArgs += "--slow" }

 # Add test selection options
 if ($Specific) {
 $baseArgs += "--specific"
 $baseArgs += $Specific
 }
 if ($Keyword) {
 $baseArgs += "-k"
 $baseArgs += $Keyword
 }
 if ($Dbg) {
 $baseArgs += "--debug"
 }

 # Function to parse test counts from pytest output
 function Parse-TestCounts {
 param([string]$output)
 
 $counts = @{
 passed = 0
 failed = 0
 error = 0
 skipped = 0
 xfailed = 0
 xpassed = 0
 warnings = 0
 }
 
 if ([string]::IsNullOrWhiteSpace($output)) {
 return $counts
 }
 
 # Look for pytest summary line like: "5 passed, 1 failed, 1 error, 1 skipped, 1 xfailed in 0.50s"
 # Pytest outputs this at the end of test execution
 # Also handle formats like "5 passed in 0.50s" or "5 passed, 1 failed"
 # For two-phase runs (parallel + serial), we need to find BOTH summary lines and combine them
 
 # Split output into lines and search backwards from the end for the summary
 $lines = $output -split "[\r\n]+"
 
 # Track counts from both phases
 $phase1Counts = @{
 passed = 0
 failed = 0
 error = 0
 skipped = 0
 xfailed = 0
 xpassed = 0
 warnings = 0
 }
 $phase2Counts = @{
 passed = 0
 failed = 0
 error = 0
 skipped = 0
 xfailed = 0
 xpassed = 0
 warnings = 0
 }
 
 $foundPhase2 = $false
 $foundPhase1 = $false
 
 for ($i = $lines.Length - 1; $i -ge 0; $i--) {
 $line = $lines[$i].Trim()
 
 # Check if this looks like a pytest summary line
 # Pytest summary lines look like: "7 failed, 185 passed, 1 error in 14.46s"
 # They must contain "in X.XXs" timing AND test result keywords
 # OR be wrapped in '=' separators (like "====== 7 failed, 1 passed in 0.50s ======")
 # This avoids matching "collected N items / M error / N deselected" lines
 $hasTimingInfo = $line -match '\bin\s+\d+\.\d+s\b'
 $hasTestResults = $line -match '\d+\s+(passed|failed|error|skipped|xfailed|xpassed|warning)'
 $hasSeparators = $line -match '^=+.*=+$'
 $isSummaryLine = ($hasTestResults -and $hasTimingInfo) -or ($hasSeparators -and $hasTestResults)
 
 if ($isSummaryLine) {
 # Skip lines that only have "deselected" without actual test results
 if (($line -match 'deselected') -and -not ($line -match '\b\d+\s+(passed|failed|error)\b')) {
 continue
 }
 
 # Extract counts using regex - match patterns like "5 passed", "1 failed", etc.
 $lineCounts = @{
 passed = 0
 failed = 0
 error = 0
 skipped = 0
 xfailed = 0
 xpassed = 0
 warnings = 0
 }
 
 if ($line -match '\b(\d+)\s+passed\b') {
 $lineCounts.passed = [int]$matches[1]
 }
 if ($line -match '\b(\d+)\s+failed\b') {
 $lineCounts.failed = [int]$matches[1]
 }
 if ($line -match '\b(\d+)\s+error') {
 $lineCounts.error = [int]$matches[1]
 }
 if ($line -match '\b(\d+)\s+skipped\b') {
 $lineCounts.skipped = [int]$matches[1]
 }
 if ($line -match '\b(\d+)\s+xfailed\b') {
 $lineCounts.xfailed = [int]$matches[1]
 }
 if ($line -match '\b(\d+)\s+xpassed\b') {
 $lineCounts.xpassed = [int]$matches[1]
 }
 if ($line -match '\b(\d+)\s+warning') {
 $lineCounts.warnings = [int]$matches[1]
 }
 
 # If we found at least one count (passed, failed, or error), this is a valid summary line
 if ($lineCounts.passed -gt 0 -or $lineCounts.failed -gt 0 -or $lineCounts.error -gt 0) {
 # First summary line found (reading backwards) is Phase 2 (serial)
 if (-not $foundPhase2) {
 $phase2Counts = $lineCounts
 $foundPhase2 = $true
 }
 # Second summary line is Phase 1 (parallel)
 elseif (-not $foundPhase1) {
 $phase1Counts = $lineCounts
 $foundPhase1 = $true
 break # We have both phases now
 }
 }
 }
 }
 
 # Combine counts from both phases (or use single phase if only one found)
 if ($foundPhase1 -and $foundPhase2) {
 # Two-phase run: combine counts
 $counts.passed = $phase1Counts.passed + $phase2Counts.passed
 $counts.failed = $phase1Counts.failed + $phase2Counts.failed
 $counts.error = $phase1Counts.error + $phase2Counts.error
 $counts.skipped = $phase1Counts.skipped + $phase2Counts.skipped
 $counts.xfailed = $phase1Counts.xfailed + $phase2Counts.xfailed
 $counts.xpassed = $phase1Counts.xpassed + $phase2Counts.xpassed
 $counts.warnings = $phase1Counts.warnings + $phase2Counts.warnings
 }
 elseif ($foundPhase2) {
 # Only one phase found (single-phase run or Phase 1 had no tests)
 $counts = $phase2Counts
 }
 # If neither phase found, counts remain at 0 (already initialized)
 
 return $counts
 }

 # Run tests for each project
 $results = @{}
 $totalProjects = $projectsToTest.Count
 $currentProject = 0

 foreach ($project in $projectsToTest) {
 $currentProject++
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "[$currentProject/$totalProjects] Testing: $project" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host ""

 # Build arguments for this project
 $projectArgs = @($testProjectScript) + $baseArgs + @($project)

 # Run test_project.py - use Tee-Object with temp file to display in real-time and capture
 $tempFile = [System.IO.Path]::GetTempFileName()
 try {
 # Run and capture output to temp file while displaying in real-time
 # Set ErrorAction to Continue for this command to avoid treating Python stderr as PowerShell errors
 $ErrorActionPreference_Saved = $ErrorActionPreference
 $ErrorActionPreference = "Continue"
 & python @projectArgs 2>&1 | Tee-Object -FilePath $tempFile
 $exitCode = $LASTEXITCODE
 $ErrorActionPreference = $ErrorActionPreference_Saved

 # Read captured output for parsing
 $outputString = Get-Content -Path $tempFile -Raw
 } finally {
 # Clean up temp file
 if (Test-Path $tempFile) {
 Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
 }
 }

 # Parse test counts from output
 $testCounts = Parse-TestCounts -output $outputString

 # Resolve THIS run's artifacts from the exact paths the runner itself printed.
 #
 # The run directory must never be guessed -- not by rebuilding its name from a
 # 'test-results-<timestamp>' regex, and not by picking the newest directory under
 # .test_results. Both guesses silently attach another run's results to this one
 # whenever a second test.ps1 is in flight against the same package (the exact
 # failure mode of task 17-14: a -Specific run reporting a different file's tests).
 # TestRunner always emits an absolute path for the run it owns:
 #   quiet mode   -> "Details: <run>/index.json"  (or "Log: <run>/full.log")
 #   verbose mode -> "Structured test results: <run>/index.json" and "Log file: <run>/full.log"
 # If none of those appear, this run produced no attributable artifacts; say so
 # rather than adopting a directory that belongs to someone else.
 $projectLogPath = $null
 $projectIndexPath = $null
 if ($outputString) {
 if ($outputString -match '(?m)^\s*(?:Details|Structured test results):\s+([^\r\n]+index\.json)\s*$') {
 $projectIndexPath = $matches[1].Trim()
 }
 if ($outputString -match '(?m)^\s*(?:Log file|Log):\s+([^\r\n]+full\.log)\s*$') {
 $projectLogPath = $matches[1].Trim()
 }

 # Each path implies the other: they are siblings inside the one run directory.
 if ($projectIndexPath -and -not $projectLogPath) {
 $candidate = Join-Path (Split-Path $projectIndexPath -Parent) "full.log"
 if (Test-Path $candidate) { $projectLogPath = $candidate }
 }
 if ($projectLogPath -and -not $projectIndexPath) {
 $candidate = Join-Path (Split-Path $projectLogPath -Parent) "index.json"
 if (Test-Path $candidate) { $projectIndexPath = $candidate }
 }

 if ($projectIndexPath -and -not (Test-Path $projectIndexPath)) { $projectIndexPath = $null }
 if ($projectLogPath -and -not (Test-Path $projectLogPath)) { $projectLogPath = $null }

 if (-not $projectLogPath -and -not $projectIndexPath -and -not $NoSave) {
 Write-Host "  (no run directory reported by the test runner for $project - results were not saved)" -ForegroundColor Yellow
 }
 }

 # Store detailed results
 $results[$project] = @{
 success = ($exitCode -eq 0)
 passed = $testCounts.passed
 failed = $testCounts.failed
 error = $testCounts.error
 skipped = $testCounts.skipped
 xfailed = $testCounts.xfailed
 xpassed = $testCounts.xpassed
 warnings = $testCounts.warnings
 logPath = $projectLogPath
 }

 # Append AI prompt to project log file if there are failures, errors, or warnings
 if ($projectLogPath -and (Test-Path $projectLogPath) -and 
 ($testCounts.failed -gt 0 -or $testCounts.error -gt 0 -or $testCounts.warnings -gt 0)) {
 try {
 $promptParts = @()
 if ($testCounts.failed -gt 0) {
 $promptParts += "$($testCounts.failed) failures"
 }
 if ($testCounts.error -gt 0) {
 $promptParts += "$($testCounts.error) errors"
 }
 if ($testCounts.warnings -gt 0) {
 $promptParts += "$($testCounts.warnings) warning"
 }
 
 if ($projectIndexPath -and (Test-Path $projectIndexPath)) {
 $absoluteIndexPath = [System.IO.Path]::GetFullPath($projectIndexPath)
 $prompt = @"

<--->
Read $absoluteIndexPath and fix failures by cluster. $($promptParts -join ', ') found.
<--->
"@
 } else {
 $absoluteProjectLogPath = [System.IO.Path]::GetFullPath($projectLogPath)
 $prompt = @"

<--->
Peruse $absoluteProjectLogPath and fix $($promptParts -join ', ').
<--->
"@
 }

 # Append to project log file (always append to the log, not index.json)
 $utf8Encoding = New-Object System.Text.UTF8Encoding($false)
 [System.IO.File]::AppendAllText($projectLogPath, $prompt, $utf8Encoding)
 } catch {
 Write-Warning "Failed to append AI prompt to project log file: $_"
 }
 }

 if ($exitCode -eq 0) {
 Write-Host ""
 Write-Host "[PASS] Tests passed for $project" -ForegroundColor Green
 } else {
 Write-Host ""
 Write-Host "[FAIL] Tests failed for $project (exit code: $exitCode)" -ForegroundColor Red
 }
 }

 # Print summary
 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "Test Summary" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan

 # @(...) forces an array. Without it, a single surviving result is returned as a
 # bare Hashtable, and .Count on a Hashtable is its KEY count (9) -- so a one-project
 # run printed "Passed: 9".
 $passed = @($results.Values | Where-Object { $_.success -eq $true }).Count
 $failed = @($results.Values | Where-Object { $_.success -eq $false }).Count

 foreach ($project in ($results.Keys | Sort-Object)) {
 $result = $results[$project]
 $status = if ($result.success) { "[PASS]" } else { "[FAIL]" }
 $color = if ($result.success) { "Green" } else { "Red" }
 
 # Build test counts string
 $testInfo = @()
 if ($result.passed -gt 0) { $testInfo += "pass: $($result.passed)" }
 if ($result.failed -gt 0) { $testInfo += "fail: $($result.failed)" }
 if ($result.error -gt 0) { $testInfo += "error: $($result.error)" }
 if ($result.skipped -gt 0) { $testInfo += "skip: $($result.skipped)" }
 if ($result.xfailed -gt 0) { $testInfo += "xfail: $($result.xfailed)" }
 if ($result.xpassed -gt 0) { $testInfo += "xpass: $($result.xpassed)" }
 
 $testInfoStr = if ($testInfo.Count -gt 0) { " ($($testInfo -join ', '))" } else { "" }
 
 Write-Host " $status : $project$testInfoStr" -ForegroundColor $color
 }

 Write-Host ""
 Write-Host "Total: $totalProjects | Passed: $passed | Failed: $failed" -ForegroundColor Cyan

 # Exit with appropriate code
 if ($failed -gt 0) {
 exit 1
 } else {
 exit 0
 }

} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 # Ensure virtual environment is deactivated even on Ctrl-C
 Invoke-Cleanup
}
