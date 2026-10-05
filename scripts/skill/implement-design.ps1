#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Implement a design through tasks: operationalize -> orchestrate -> verify -> absorb, each step
    a fresh headless session on its own skill's model.

.DESCRIPTION
    The script form of /implement-design's tasks path. Typed in one session, the skill runs every
    step on its own model, because a skill invoked from another skill runs on the caller's; here
    each step is typed into its own `claude -p` run, so /operationalize-design, /task-orchestrator,
    /verify-implementation and /absorb-design each run on what their frontmatter says.

    The checks between steps are done by scripts, not by a model:
      * operationalize must create a new phase (latest-phase.ps1 before/after); when it does not,
        it stopped for a decision: the script prints its reply and the session to answer it in.
      * the phase is closed only when phase-status.ps1 shows every task completed with no
        How-Solved red flag and the design's Status line reads Implemented; otherwise the
        orchestrator runs again (up to -MaxRounds).
      * absorb runs only after verify replies "Design conformance: PROVEN"; on INCOMPLETE the
        orchestrator and verify run again (up to -MaxRounds).

    Every step's JSON result and stderr are kept under <workspace>\.tmp\skill-chain\<timestamp>\.
    Exit codes: 0 the design is absorbed; 1 a step ended in error or a check failed; 2 a step
    stopped for a decision only Jon can make (its reply and session id are printed).

.PARAMETER Design
    The design document to implement.

.PARAMETER StartAt
    The step to start at (operationalize | orchestrate | verify | absorb), to resume after answering
    a question. Every step after operationalize needs -Phase.

.PARAMETER Phase
    With -StartAt after operationalize: the phase the design was operationalized into.

.PARAMETER KeepSource
    Pass KEEP SOURCE: true to /absorb-design.

.PARAMETER Resume
    Carry one session through every step instead of a fresh session per step. Every step then
    re-reads the previous steps' whole transcript on each turn; fresh sessions are cheaper for
    long steps.

.PARAMETER PermissionMode
    The permission mode of every step. Default: auto. The guards run in every mode.

.PARAMETER MaxBudgetUsd
    Stop a step that passes this list-price cost. Default: no cap.

.PARAMETER MaxRounds
    How many times the orchestrator (and verify) may run before the chain gives up. Default: 3.

.PARAMETER Quiet
    Show only each step's prompt and summary line. By default every agent message, tool call
    and refused tool call is printed as it happens.

.PARAMETER DryRun
    Print the steps that would run, and run none.

.EXAMPLE
    .\implement-design.ps1 -Design "D:\datrix\design\<the design>.md"

.EXAMPLE
    .\implement-design.ps1 -Design "D:\datrix\design\<the design>.md" -StartAt orchestrate -Phase 52
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string]$Design = "",
    [ValidateSet("operationalize", "orchestrate", "verify", "absorb")] [string]$StartAt = "operationalize",
    [int]$Phase = 0,
    [switch]$KeepSource,
    [switch]$Resume,
    [ValidateSet("auto", "acceptEdits", "dontAsk", "bypassPermissions")] [string]$PermissionMode = "auto",
    [double]$MaxBudgetUsd = 0,
    [int]$MaxRounds = 3,
    [switch]$DryRun,
    [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$scriptsDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$workspace = Split-Path -Parent (Split-Path -Parent $scriptsDir)
Import-Module (Join-Path $scriptsDir "skill\SkillChain.psm1") -Force
$latestPhaseScript = Join-Path $scriptsDir "tasks\latest-phase.ps1"
$phaseStatusScript = Join-Path $scriptsDir "tasks\phase-status.ps1"
$ImplementedPattern = "(?m)^\W*Status:\W*Implemented"

if (-not $Design -or -not (Test-Path $Design)) {
    Write-Host "Pass the design document: -Design <path> (got '$Design'). Get-Help .\implement-design.ps1 -Full." -ForegroundColor Red
    exit 1
}
$designPath = (Resolve-Path $Design).Path
$order = @("operationalize", "orchestrate", "verify", "absorb")
$first = [array]::IndexOf($order, $StartAt)
if ($first -gt 0 -and $Phase -le 0) {
    Write-Host "-StartAt $StartAt needs -Phase: the phase the design was operationalized into." -ForegroundColor Red
    exit 1
}

Initialize-SkillChain -Workspace $workspace -Resume:$Resume -PermissionMode $PermissionMode -MaxBudgetUsd $MaxBudgetUsd -DryRun:$DryRun -Quiet:$Quiet

function Get-LatestPhase {
    $value = (& powershell -NoProfile -File $latestPhaseScript -BaseDir $workspace | Select-Object -Last 1)
    if (-not "$value".Trim()) { return 0 }
    return [int]"$value".Trim()
}

function Test-PhaseClosed {
    param([int]$Number)
    & powershell -NoProfile -File $phaseStatusScript $Number -BaseDir $workspace | Out-Null
    if ($LASTEXITCODE -ne 0) { return "phase-status.ps1 failed for phase $Number" }
    $statusPath = Join-Path $workspace (".tmp\tasks\phase-{0:D2}-status.json" -f $Number)
    $status = Get-Content -Raw -Encoding UTF8 $statusPath | ConvertFrom-Json
    $open = @($status.tasks | Where-Object { -not $_.is_completed -or @($_.how_solved_redflags).Count -gt 0 })
    if ($open.Count -gt 0) {
        return "phase $Number is not closed: " + (($open | ForEach-Object { $_.task_id }) -join ", ")
    }
    if (-not ((Get-Content -Raw -Encoding UTF8 $designPath) -match $ImplementedPattern)) {
        return "every task of phase $Number is completed, but the design's Status line is not Implemented"
    }
    return ""
}

function Invoke-Orchestration {
    param([string]$Number)
    for ($round = 1; $round -le $MaxRounds; $round++) {
        $row = Invoke-ChainStep "orchestrate" "/task-orchestrator`nPHASE: $Number"
        if ($row.DryRun) { return }
        if ($row.IsError) { Stop-Chain 1 "The orchestrator ended in error ($($row.Subtype))." $row }
        $open = Test-PhaseClosed $Number
        if (-not $open) { return }
        Write-Host "Round $round of $MaxRounds left the phase open: $open" -ForegroundColor Yellow
    }
    Stop-Chain 1 "Phase $Number is still open after $MaxRounds orchestrator run(s): $(Test-PhaseClosed $Number)" $row
}

$number = "$Phase"
if ($first -le 0) {
    $before = Get-LatestPhase
    $row = Invoke-ChainStep "operationalize" "/operationalize-design`nDOCUMENT: $designPath"
    if ($row.DryRun) {
        $number = "<the phase operationalize creates>"
    } else {
        if ($row.IsError) { Stop-Chain 1 "/operationalize-design ended in error ($($row.Subtype))." $row }
        $created = Get-LatestPhase
        if ($created -le $before) {
            Stop-Chain 2 ("/operationalize-design created no phase, so it stopped for a decision. Answer it in " +
                "its session, then rerun with -StartAt orchestrate -Phase <the phase it creates>.") $row
        }
        $number = "$created"
        Write-Host "Operationalized into phase $number." -ForegroundColor Green
    }
}

if ($first -le 1) { Invoke-Orchestration $number }

if ($first -le 2) {
    Invoke-DesignVerify -Prompt "/verify-implementation`nDESIGN: $designPath`nTASKS: $number" -MaxRounds $MaxRounds `
        -OnIncomplete { param($report) Invoke-Orchestration $number }
}

Invoke-DesignAbsorb -DesignPath $designPath -KeepSource:$KeepSource
Complete-Chain
