#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run coverage-driven test generation for one or more Datrix projects.
.DESCRIPTION
 Activates the shared virtual environment and runs metrics/lib/test_gen.py.
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
.PARAMETER MaxPromptTokens
 Approximate prompt token budget before warnings are emitted (default: 6000).
.PARAMETER VerbosePrompts
 Print generated prompts for debugging.
.PARAMETER LocalMachines
 Machines to search for local model servers, in preference order. Omit to search the
 default list in common/lib/datrix_scripts/local_llm.py.
.PARAMETER Model
 Models to use for generation, best first. Omit to use any model already in memory.
.PARAMETER LlmTimeout
 Request timeout in seconds for each generation attempt (default: 300).
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
 [int]$MaxPromptTokens = 6000,
 [switch]$VerbosePrompts,
 [string[]]$LocalMachines = @(),
 [string[]]$Model = @(),
 [int]$LlmTimeout = 300,
 [switch]$StopOnError,
 [switch]$VerboseOutput
)
$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force
$workspaceRoot = Get-DatrixWorkspaceRoot
$libraryScript = Join-Path $PSScriptRoot "lib\test_gen.py"
if ($Generate -and $GenerateAll) {
 Write-Host "ERROR: Use only one of -Generate or -GenerateAll." -ForegroundColor Red
 exit 1
}
if ($Generate) { $Mode = "generate" }
if ($GenerateAll) { $Mode = "generate-all" }
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
  # Not $args: that is PowerShell's automatic variable for unbound arguments.
  $pyArgs = @(
   "--project-root", $projectRoot,
   "--mode", $Mode,
   "--max-retries", "$MaxRetries",
   "--min-uncovered-ratio", "$MinUncoveredRatio",
   "--max-prompt-tokens", "$MaxPromptTokens"
  )
  if ($TargetFunction) {
   $pyArgs += @("--target-function", $TargetFunction)
  }
  $pyArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $Model -LlmTimeoutSeconds $LlmTimeout
  if ($VerbosePrompts) {
   $pyArgs += "--verbose-prompts"
  }
  $exitCode = Invoke-DatrixPythonScript -Script $libraryScript -Arguments $pyArgs
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
