#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Run the same generation test set for every registered language and compare per-project results.

.DESCRIPTION
  Sweeps every registered datrix.languages target (discovered at runtime -- never a
  hardcoded python/typescript pair -- so a newly installed datrix-codegen-<lang>
  package is compared with no edit here). Invokes generate.ps1 (default) or
  run-complete.ps1 with -Skip4 -Skip5 for each language, then parses the latest
  generate-results-*.log after each run from <workspace>/.generated/.results. Emits a
  Markdown table with one column per language to stdout and exits non-zero if any
  project failed in any language, a project is missing from a log, or outcomes
  differ across languages (parity gap).

.PARAMETER TestSet
  Name of the test set in scripts/config/test-projects.json (default: typescript-validation).

.PARAMETER Platform
  docker (default: docker).

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

# Runtime-validate -Platform against the installed datrix.platforms plugins
# (DI-6 / D4 open identity) rather than a static ValidateSet, so a
# newly installed datrix-codegen-<provider> package is selectable here with no
# edit to this script.
. (Join-Path $commonDir "venv.ps1")
$venvActivated = Ensure-DatrixVenv
if (-not $venvActivated) {
    throw "Could not activate the Datrix Python venv; cannot enumerate installed platform plugins."
}
$pythonExe = Join-Path (Get-DatrixVenvPath) "Scripts\python.exe"
$installedPlatforms = Get-DatrixInstalledPlatforms -PythonExe $pythonExe

if ($Platform -notin $installedPlatforms) {
    throw "Platform '$Platform' is not an installed datrix.platforms plugin. " +
          "Installed platforms: $($installedPlatforms -join ', '). " +
          "Install the corresponding datrix-codegen-<platform> package to add it."
}

# The languages to compare are the installed datrix.languages set, discovered at
# runtime (never a hardcoded python/typescript pair). A cross-language comparison
# needs at least one target; installing a new datrix-codegen-<lang> adds a column.
$installedLanguages = @(Get-DatrixInstalledLanguages -PythonExe $pythonExe)
if ($installedLanguages.Count -eq 0) {
    throw "No datrix.languages targets are installed; cannot run the language comparison."
}

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
# language name -> (project name -> status). Ordered by $installedLanguages so the
# table columns are stable across runs.
$maps = @{}

foreach ($lang in $installedLanguages) {
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
    $maps[$lang] = Read-GenerationStatusMap -LogFile $latest -LinePattern $statusLinePattern
}

$allNames = [System.Collections.Generic.HashSet[string]]::new()
foreach ($lang in $installedLanguages) {
    foreach ($k in $maps[$lang].Keys) {
        [void]$allNames.Add($k)
    }
}
$sortedProjects = @($allNames) | Sort-Object

$langHeader = ($installedLanguages -join " | ")
$langSep = (($installedLanguages | ForEach-Object { "--------" }) -join " | ")

Write-Output ""
Write-Output "## Multi-language generation results"
Write-Output ""
Write-Output "Test set: **$TestSet** | Platform: **$Platform** | Languages: **$($installedLanguages -join ', ')** | Log (latest): generation results under ``.generated/.results/``"
Write-Output ""
Write-Output "| Project | $langHeader | Parity |"
Write-Output "|---------| $langSep |--------|"

foreach ($proj in $sortedProjects) {
    $statuses = @()
    foreach ($lang in $installedLanguages) {
        $st = $maps[$lang][$proj]
        if (-not $st) {
            $st = "(missing)"
        }
        $statuses += $st
    }
    # Parity holds when every language reports the identical outcome for this project.
    $distinct = @($statuses | Select-Object -Unique)
    $parity = if ($distinct.Count -eq 1) { "OK" } else { "Mismatch" }
    if (@($statuses | Where-Object { $_ -ne "Success" }).Count -gt 0) {
        $anyFailure = $true
    }
    $row = $statuses -join " | "
    Write-Output "| $proj | $row | $parity |"
}

Write-Output ""

if ($anyFailure) {
    exit 1
}
exit 0
