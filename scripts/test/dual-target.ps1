#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Run the same generation test set for Python and TypeScript and compare per-project results.

.DESCRIPTION
  Invokes generate.ps1 (default) or run-complete.ps1 with -Skip4 -Skip5 for each language,
  then parses the latest generate-results-*.log after each run from
  <workspace>/.generated/.results. Emits a Markdown table to stdout and exits non-zero
  if any project failed in either language, a project is missing from a log, or outcomes
  differ between languages (parity gap).

.PARAMETER TestSet
  Name of the test set in scripts/config/test-projects.json (default: typescript-validation).

.PARAMETER Platform
  docker | kubernetes | k8s (default: docker).

.PARAMETER Skip4
  When used with -Skip5, runs run-complete.ps1 instead of generate.ps1 (workflow steps 1-2 only).

.PARAMETER Skip5
  When used with -Skip4, runs run-complete.ps1 instead of generate.ps1.

.PARAMETER FreshBuild
  Force fresh Docker builds (--no-cache) for deployment tests when using run-complete.ps1.

.PARAMETER Dbg
  Forward debug logging to the child script (-Dbg on generate.ps1, -Dbg on run-complete.ps1).
#>

[CmdletBinding()]
param(
    [string]$TestSet = "typescript-validation",

    [Parameter()]
    [ValidateSet("docker", "kubernetes", "k8s")]
    [string]$Platform = "docker",

    [switch]$Skip4,
    [switch]$Skip5,
    [switch]$FreshBuild,

    [Alias("Dbg")]
    [switch]$DebugLogging
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$datrixScriptsRoot = Split-Path -Parent $scriptDir
$commonDir = Join-Path $datrixScriptsRoot "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force

$datrixWorkspaceRoot = Get-DatrixWorkspaceRoot -ScriptPath $MyInvocation.MyCommand.Path
$generateScript = Join-Path (Join-Path $datrixScriptsRoot "dev") "generate.ps1"
$runCompleteScript = Join-Path $scriptDir "run-complete.ps1"

$resultsDir = Join-Path (Join-Path $datrixWorkspaceRoot ".generated") ".results"
$statusLinePattern = '^\s*\[(\d+)/(\d+)\]\s+([^:]+):\s+(Success|Failed)\s*$'

function Get-LatestGenerateResultsLog {
    param([string]$ResultsDirPath)
    if (-not (Test-Path -LiteralPath $ResultsDirPath)) {
        throw "Results directory not found: $ResultsDirPath"
    }
    $logs = Get-ChildItem -LiteralPath $ResultsDirPath -Filter "generate-results-*.log" -File -ErrorAction SilentlyContinue
    if (-not $logs) {
        throw "No generate-results-*.log files found in $ResultsDirPath"
    }
    return $logs | Sort-Object Name -Descending | Select-Object -First 1
}

function Read-GenerationStatusMap {
    param(
        [System.IO.FileInfo]$LogFile,
        [string]$LinePattern
    )
    $map = @{}
    $content = Get-Content -LiteralPath $LogFile.FullName -Encoding UTF8
    foreach ($line in $content) {
        if ($line -match $LinePattern) {
            $projectName = $matches[3].Trim()
            $map[$projectName] = $matches[4]
        }
    }
    return $map
}

if (-not (Test-Path -LiteralPath $generateScript)) {
    Write-Error "generate.ps1 not found at: $generateScript"
    exit 1
}
if (-not (Test-Path -LiteralPath $runCompleteScript)) {
    Write-Error "run-complete.ps1 not found at: $runCompleteScript"
    exit 1
}

$useRunComplete = $Skip4 -and $Skip5

$anyFailure = $false
$maps = @{
    Python     = $null
    TypeScript = $null
}

foreach ($entry in @(
        @{ Lang = "python"; Label = "Python" },
        @{ Lang = "typescript"; Label = "TypeScript" }
    )) {
    $lang = $entry.Lang
    $label = $entry.Label

    if ($useRunComplete) {
        $childArgs = @(
            "-TestSet", $TestSet,
            "-Language", $lang,
            "-Platform", $Platform,
            "-Skip4",
            "-Skip5"
        )
        if ($FreshBuild) {
            $childArgs += "-FreshBuild"
        }
        if ($DebugLogging) {
            $childArgs += "-Dbg"
        }
        & $runCompleteScript @childArgs
    }
    else {
        $childArgs = @(
            "-TestSet", $TestSet,
            "-Language", $lang,
            "-Platform", $Platform
        )
        if ($DebugLogging) {
            $childArgs += "-Dbg"
        }
        & $generateScript @childArgs
    }

    if ($LASTEXITCODE -ne 0) {
        $anyFailure = $true
    }

    $latest = Get-LatestGenerateResultsLog -ResultsDirPath $resultsDir
    $maps[$label] = Read-GenerationStatusMap -LogFile $latest -LinePattern $statusLinePattern
}

$allNames = [System.Collections.Generic.HashSet[string]]::new()
foreach ($label in @("Python", "TypeScript")) {
    foreach ($k in $maps[$label].Keys) {
        [void]$allNames.Add($k)
    }
}
$sortedProjects = @($allNames) | Sort-Object

Write-Output ""
Write-Output "## Dual-target generation results"
Write-Output ""
Write-Output "Test set: **$TestSet** | Platform: **$Platform** | Log (latest): generation results under ``.generated/.results/``"
Write-Output ""
Write-Output "| Project | Python | TypeScript | Parity |"
Write-Output "|---------|--------|------------|--------|"

foreach ($proj in $sortedProjects) {
    $pySt = $maps["Python"][$proj]
    $tsSt = $maps["TypeScript"][$proj]
    if (-not $pySt) {
        $pySt = "(missing)"
    }
    if (-not $tsSt) {
        $tsSt = "(missing)"
    }
    $parity = if ($pySt -eq $tsSt) { "OK" } else { "Mismatch" }
    if ($pySt -ne "Success" -or $tsSt -ne "Success") {
        $anyFailure = $true
    }
    Write-Output "| $proj | $pySt | $tsSt | $parity |"
}

Write-Output ""

if ($anyFailure) {
    exit 1
}
exit 0
