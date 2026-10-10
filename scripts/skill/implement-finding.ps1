#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Work through the first findings files of the inbox one at a time: one fresh session per finding
    checks it against the code, fixes it when it still holds, and the script deletes it once proven.

.DESCRIPTION
    The multi-finding form of /implement-finding. For each selected finding, in name order, one
    headless /implement-finding session on -Model ends with one line:
      Finding fix: ALREADY RESOLVED   the code no longer has the defect; nothing was changed
      Finding fix: DONE               fixed, with a tagged test and targeted test runs
      Finding fix: BLOCKED B<n>       stopped with a B1-B4 proof; the finding stays for Jon

    The session never deletes the finding; the script does, through skill-assist finding-close
    (skill\lib\implement_finding.py), not on a model's word: never while another findings file
    names it, and after DONE only when the session's last foreground test.ps1 run passed (read
    from the step's stream log). Each finding is closed before the next one starts.

    Step logs: <workspace>\.tmp\skill-chain\<timestamp>\.

    Exit codes: 0 every selected finding is deleted; 1 a step ended in error, replied with no
    outcome line, or a finding was left in place; 2 no failure, but at least one session stopped
    for a decision only Jon can make.

.PARAMETER Count
    How many findings files to take, first by name. Default: 10.

.PARAMETER Finding
    Work these findings files instead of the first -Count of the inbox.

.PARAMETER Dir
    The findings folder. Default: <workspace>\reports\finding.

.PARAMETER Model
    The model of each session. Default: claude-opus-5-5.

.PARAMETER Effort
    The effort of each session. Default: high.

.PARAMETER PermissionMode
    The permission mode of every session. Default: auto. The guards run in every mode.

.PARAMETER MaxBudgetUsd
    Stop a session that passes this list-price cost. Default: no cap.

.PARAMETER Quiet
    Show only each session's prompt and summary line.

.PARAMETER DryRun
    List the selected findings and print the sessions that would run; run none.

.EXAMPLE
    .\implement-finding.ps1

.EXAMPLE
    .\implement-finding.ps1 -Count 3 -DryRun

.EXAMPLE
    .\implement-finding.ps1 -Finding "D:\datrix\reports\finding\<the finding>.md"
#>
[CmdletBinding()]
param(
    [int]$Count = 10,
    [string[]]$Finding = @(),
    [string]$Dir = "",
    [string]$Model = "claude-opus-5-5",
    [ValidateSet("low", "medium", "high", "xhigh", "max")] [string]$Effort = "high",
    [ValidateSet("auto", "acceptEdits", "dontAsk", "bypassPermissions")] [string]$PermissionMode = "auto",
    [double]$MaxBudgetUsd = 0,
    [switch]$DryRun,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$workspace = Split-Path -Parent (Split-Path -Parent $scriptsDir)
$checkScript = Join-Path $scriptDir "lib\skill_assist.py"
. (Join-Path $scriptsDir "common\venv.ps1")
Import-Module (Join-Path $scriptDir "SkillChain.psm1") -Force

$ExitDeleted = 0
$OutcomePattern = "Finding fix:[ \t*_`]*(DONE|ALREADY RESOLVED|BLOCKED\W*(B[1-4]))"
$pythonExe = Join-Path (Get-DatrixVenvPath) "Scripts\python.exe"

function Invoke-FindingClose {
    <# Run skill-assist finding-close; print its output; return its exit code. #>
    param([Parameter(Mandatory)] [string]$Path, [string]$SessionLog = "")
    $closeArgs = @("--workspace", $workspace, "finding-close", "--finding", $Path)
    if ($SessionLog) { $closeArgs += @("--session-log", $SessionLog) }
    & $pythonExe $checkScript @closeArgs | ForEach-Object { Write-Host "  $_" }
    return $LASTEXITCODE
}

function Get-SelectedFindings {
    if ($Finding.Count -gt 0) {
        foreach ($path in $Finding) {
            if (-not (Test-Path -LiteralPath $path -PathType Leaf)) {
                Write-Host "Finding file not found: $path. Pass existing files to -Finding." -ForegroundColor Red
                exit 1
            }
        }
        return @($Finding | ForEach-Object { (Resolve-Path -LiteralPath $_).Path })
    }
    $selectArgs = @("--workspace", $workspace, "finding-select", "--count", "$Count")
    if ($Dir) { $selectArgs += @("--dir", $Dir) }
    $paths = @(& $pythonExe $checkScript @selectArgs)
    if ($LASTEXITCODE -ne 0) {
        Write-Host "Selecting the findings failed (exit $LASTEXITCODE)." -ForegroundColor Red
        exit 1
    }
    return $paths
}

function Get-Outcome {
    <# The last outcome line of the session: its Match, or $null when it replied with none. #>
    param([Parameter(Mandatory)] [object]$Row)
    $found = [regex]::Matches(((Get-SessionReplies $Row) -join "`n"), $OutcomePattern)
    if ($found.Count -eq 0) { return $null }
    return $found[$found.Count - 1]
}

function Resolve-Finding {
    <# One session checks and fixes the finding; the script closes it. Returns its outcome. #>
    param([Parameter(Mandatory)] [string]$Path)
    $row = Invoke-ChainStep "fix" "/implement-finding`nFINDING: $Path`nCLOSE: script" -Model $Model -Effort $Effort
    if ($row.DryRun) { return "dry run" }
    $resume = "claude --resume $($row.SessionId)"
    if ($row.IsError) { return "FAILED: the session ended in error ($($row.Subtype)); $resume" }
    if (-not (Test-Path -LiteralPath $Path)) { return "FAILED: the session deleted the finding itself, so its tests were not checked; $resume" }
    $outcome = Get-Outcome $row
    if (-not $outcome) { return "FAILED: the session replied with no 'Finding fix:' line; $resume" }
    if ($outcome.Groups[2].Success) { return "NEEDS JON: stopped $($outcome.Groups[2].Value); $resume" }
    if ($outcome.Groups[1].Value -eq "ALREADY RESOLVED") {
        if ((Invoke-FindingClose $Path) -eq $ExitDeleted) { return "deleted (no longer an issue)" }
        return "FAILED: already resolved, but not deletable (see above); $resume"
    }
    if ((Invoke-FindingClose $Path $row.StreamPath) -eq $ExitDeleted) { return "fixed and deleted" }
    return "FAILED: fixed, but left in place (see above); $resume"
}

# Run from a prompt (.\implement-finding.ps1), an activation made here would outlive the script;
# every exit below, Ctrl-C included, passes through the finally that undoes it. A venv the caller
# had already activated is left as it was.
$venvWasActive = [bool]$env:VIRTUAL_ENV
try {
    if (-not (Ensure-DatrixVenv)) {
        Write-Host "Failed to activate the workspace virtual environment." -ForegroundColor Red
        exit 1
    }

    $selected = @(Get-SelectedFindings)
    if ($selected.Count -eq 0) {
        Write-Host "No findings files to work on."
        exit 0
    }
    Write-Host "Findings ($($selected.Count)):"
    $selected | ForEach-Object { Write-Host "  $_" }

    Initialize-SkillChain -Workspace $workspace -PermissionMode $PermissionMode -MaxBudgetUsd $MaxBudgetUsd -DryRun:$DryRun -Quiet:$Quiet

    $outcomes = @{}
    $number = 0
    foreach ($path in $selected) {
        $number += 1
        Write-Host ""
        Write-Host "##### finding $number of $($selected.Count): $([System.IO.Path]::GetFileName($path))" -ForegroundColor Magenta
        if (-not $DryRun -and -not (Test-Path -LiteralPath $path)) {
            $outcomes[$path] = "already gone"
            continue
        }
        $outcomes[$path] = Resolve-Finding $path
    }

    Write-ChainSummary
    Write-Host "=== findings ===" -ForegroundColor Cyan
    $rows = @($selected | ForEach-Object { [pscustomobject]@{ Finding = [System.IO.Path]::GetFileName($_); Outcome = $outcomes[$_] } })
    $rows | Format-Table Finding, Outcome -AutoSize -Wrap | Out-String | Write-Host
    if (@($rows | Where-Object { $_.Outcome -like "FAILED*" }).Count -gt 0) { exit 1 }
    if (@($rows | Where-Object { $_.Outcome -like "NEEDS JON*" }).Count -gt 0) { exit 2 }
    exit 0
} finally {
    if (-not $venvWasActive) { Disable-DatrixVenv }
}
