#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run coverage-driven test generation for one or more Datrix projects.
.DESCRIPTION
 Activates the shared virtual environment and runs library/metrics/test_gen.py.
 Modes:
 - report       : list uncovered functions ranked by priority
 - generate     : generate test for top-ranked (or target) function
 - generate-all : generate tests for all ranked candidates
.PARAMETER Projects
 One or more project names or folder paths (e.g., datrix-common, .\datrix-common\).
.PARAMETER All
 Run for all Datrix projects (datrix-* folders, excluding datrix).
.PARAMETER Mode
 report | generate | generate-all (default: report).
.PARAMETER Generate
 Shortcut for -Mode generate.
.PARAMETER GenerateAll
 Shortcut for -Mode generate-all.
.PARAMETER TargetFunction
 Optional function name to target in generate mode.
.PARAMETER MaxRetries
 Maximum generation retries per function (default: 3).
.PARAMETER MinUncoveredRatio
Include only functions where uncovered/total lines > ratio (default: 0.5).
.PARAMETER OllamaUrl
 Ollama server URL used for generation (default: http://10.94.0.100:11434).
.PARAMETER Model
 Override the Ollama model used for generation.
.PARAMETER StopOnError
Stop after first project failure.
.PARAMETER VerboseOutput
 Enables verbose wrapper output.
#>
[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,
 [switch]$All,
 [ValidateSet("report", "generate", "generate-all")]
 [string]$Mode = "report",
 [switch]$Generate,
 [switch]$GenerateAll,
 [string]$TargetFunction,
 [int]$MaxRetries = 3,
 [double]$MinUncoveredRatio = 0.5,
 [string]$OllamaUrl = "http://10.94.0.100:11434",
 [string]$Model,
 [switch]$StopOnError,
 [switch]$VerboseOutput
)
$ErrorActionPreference = "Stop"
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$venvUtilsScript = Join-Path $commonDir "venv.ps1"
if (-not (Test-Path $venvUtilsScript)) {
 Write-Error "Error: Common venv utilities not found at: $venvUtilsScript"
 exit 1
}
. $venvUtilsScript
$workspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path
$datrixCommon = Join-Path $workspaceRoot "datrix"
$libraryScript = Join-Path $datrixCommon "scripts\library\metrics\test_gen.py"
if (-not (Test-Path $libraryScript)) {
 Write-Error "Error: test_gen.py not found at: $libraryScript"
 exit 1
}
if ($Generate -and $GenerateAll) {
 Write-Host "ERROR: Use only one of -Generate or -GenerateAll." -ForegroundColor Red
 exit 1
}
if ($Generate) { $Mode = "generate" }
if ($GenerateAll) { $Mode = "generate-all" }
function Invoke-Cleanup { Disable-DatrixVenv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null
try {
 $projectsToRun = @()
 if ($All) {
  $projectsToRun = Get-DatrixPackageNamesGlob -WorkspaceRoot $workspaceRoot
  if ($projectsToRun.Count -eq 0) {
   Write-Host "ERROR: No Datrix projects found in: $workspaceRoot" -ForegroundColor Red
   exit 1
  }
 } elseif ($Projects.Count -gt 0) {
  $projectsToRun = ($Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }) | Where-Object { $_ -ne "datrix" }
  if ($projectsToRun.Count -eq 0) {
   Write-Host "ERROR: No valid projects specified (datrix excluded)." -ForegroundColor Red
   exit 1
  }
 } else {
  Write-Host "ERROR: No projects specified." -ForegroundColor Red
  Write-Host "Usage: .\test-gen.ps1 <project-name> [-Mode report|generate|generate-all]" -ForegroundColor Yellow
  exit 1
 }
 if (-not (Ensure-DatrixVenv)) {
  Write-Error "Failed to ensure virtual environment is ready"
  exit 1
 }
 $results = @{}
 $i = 0
 foreach ($project in $projectsToRun) {
  $i++
  if ($VerboseOutput) {
   Write-Host "[$i/$($projectsToRun.Count)] Running test-gen for $project (mode=$Mode)" -ForegroundColor Cyan
  } else {
   Write-Host "Running test-gen for $project (mode=$Mode)" -ForegroundColor Cyan
  }
  $projectRoot = Join-Path $workspaceRoot $project
  $args = @(
   $libraryScript,
   "--project-root", $projectRoot,
   "--mode", $Mode,
   "--max-retries", $MaxRetries,
   "--min-uncovered-ratio", $MinUncoveredRatio
  )
  if ($TargetFunction) {
   $args += "--target-function", $TargetFunction
  }
  if ($OllamaUrl) {
   $args += "--ollama-url", $OllamaUrl
  }
  if ($Model) {
   $args += "--model", $Model
  }
  & python @args
  $exitCode = $LASTEXITCODE
  $results[$project] = ($exitCode -eq 0)
  if ($exitCode -eq 0) {
   Write-Host "[PASS] $project" -ForegroundColor Green
  } else {
   Write-Host "[FAIL] $project (exit code: $exitCode)" -ForegroundColor Red
   if ($StopOnError) {
    Write-Host "Stopping due to -StopOnError" -ForegroundColor Red
    break
   }
  }
 }
 $failed = ($results.Values | Where-Object { $_ -eq $false }).Count
 Write-Host ""
 Write-Host "Test Generation Summary" -ForegroundColor Cyan
 foreach ($p in ($results.Keys | Sort-Object)) {
  if ($results[$p]) {
   Write-Host " [PASS] $p" -ForegroundColor Green
  } else {
   Write-Host " [FAIL] $p" -ForegroundColor Red
  }
 }
 if ($failed -gt 0) { exit 1 }
 exit 0
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
