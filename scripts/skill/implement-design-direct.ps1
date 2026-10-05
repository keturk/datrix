#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Implement a design directly, with no tasks: implement -> verify -> absorb, each step a fresh
    headless session on its own skill's model.

.DESCRIPTION
    The script form of /implement-design-direct. Typed in one session, that skill runs verify and
    absorb on its own model, because a skill invoked from another skill runs on the caller's; here
    each step is typed into its own `claude -p` run:
      implement  /implement-design-direct with STOP AFTER: implement (its Steps 1-3), on its model
      verify     /verify-implementation, TASKS: none, FILES from the ledger, on its model
      absorb     /absorb-design, on its model

    The implement step keeps its work plan in a ledger the script names:
    <workspace>\.tmp\implement-direct-<design file name>.md. The checks between steps are done by
    the script, not by a model:
      * implement is done only when the ledger exists, has no unchecked unit and has a
        "## Files changed" section. No ledger means it stopped at its gate for a decision (exit 2);
        unchecked units mean it ran out of turn, so implement runs again from the ledger (up to
        -MaxRounds).
      * absorb runs only after verify replies "Design conformance: PROVEN". On INCOMPLETE, verify's
        reply is saved and implement runs again with GAPS: <that file>, then verify again (up to
        -MaxRounds).

    Every step's JSON result and stderr are kept under <workspace>\.tmp\skill-chain\<timestamp>\.
    Exit codes: 0 the design is absorbed; 1 a step ended in error or a check failed; 2 a step
    stopped for a decision only Jon can make (its reply and session id are printed).

.PARAMETER Design
    The design document to implement.

.PARAMETER StartAt
    The step to start at (implement | verify | absorb), to resume after answering a question.

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
    How many times implement (and verify) may run before the chain gives up. Default: 3.

.PARAMETER Quiet
    Show only each step's prompt and summary line. By default every agent message, tool call
    and refused tool call is printed as it happens.

.PARAMETER DryRun
    Print the steps that would run, and run none.

.EXAMPLE
    .\implement-design-direct.ps1 -Design "D:\datrix\design\<the design>.md"

.EXAMPLE
    .\implement-design-direct.ps1 -Design "D:\datrix\design\<the design>.md" -StartAt verify
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string]$Design = "",
    [ValidateSet("implement", "verify", "absorb")] [string]$StartAt = "implement",
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
$UncheckedUnitPattern = "(?m)^\s*\|.*\[ \]"
$FilesChangedPattern = "(?m)^##\s+Files changed\s*$"

if (-not $Design -or -not (Test-Path $Design)) {
    Write-Host "Pass the design document: -Design <path> (got '$Design'). Get-Help .\implement-design-direct.ps1 -Full." -ForegroundColor Red
    exit 1
}
$designPath = (Resolve-Path $Design).Path
$ledger = Join-Path $workspace (".tmp\implement-direct-" + [System.IO.Path]::GetFileNameWithoutExtension($designPath) + ".md")
$order = @("implement", "verify", "absorb")
$first = [array]::IndexOf($order, $StartAt)
if ($first -gt 0 -and -not $DryRun -and -not (Test-Path $ledger)) {
    Write-Host "-StartAt $StartAt needs the implement step's ledger, and there is none: $ledger" -ForegroundColor Red
    exit 1
}

Initialize-SkillChain -Workspace $workspace -Resume:$Resume -PermissionMode $PermissionMode -MaxBudgetUsd $MaxBudgetUsd -DryRun:$DryRun -Quiet:$Quiet

function Get-LedgerGap {
    if (-not (Test-Path $ledger)) { return "no ledger" }
    $text = Get-Content -Raw -Encoding UTF8 $ledger
    if ($text -match $UncheckedUnitPattern) { return "unchecked units" }
    if (-not ($text -match $FilesChangedPattern)) { return "no '## Files changed' section" }
    return ""
}

function Invoke-Implementation {
    param([string]$Gaps = "")
    $prompt = "/implement-design-direct`nDOCUMENT: $designPath`nLEDGER: $ledger`nSTOP AFTER: implement"
    if ($Gaps) { $prompt += "`nGAPS: $Gaps" }
    for ($round = 1; $round -le $MaxRounds; $round++) {
        $row = Invoke-ChainStep "implement" $prompt
        if ($row.DryRun) { return }
        if ($row.IsError) { Stop-Chain 1 "/implement-design-direct ended in error ($($row.Subtype))." $row }
        $gap = Get-LedgerGap
        if (-not $gap) { return }
        if ($gap -eq "no ledger") {
            Stop-Chain 2 ("/implement-design-direct wrote no ledger, so it stopped at its gate for a decision. Answer it " +
                "in its session, then rerun this script.") $row
        }
        Write-Host "Implement round $round of $MaxRounds left the ledger with $gap; running it again." -ForegroundColor Yellow
    }
    Stop-Chain 1 "The ledger still has $(Get-LedgerGap) after $MaxRounds implement run(s): $ledger" $row
}

if ($first -le 0) { Invoke-Implementation }

if ($first -le 1) {
    $verifyPrompt = "/verify-implementation`nDESIGN: $designPath`nTASKS: none`nFILES: the files listed under '## Files changed' in $ledger"
    Invoke-DesignVerify -Prompt $verifyPrompt -MaxRounds $MaxRounds -OnIncomplete { param($report) Invoke-Implementation $report }
}

Invoke-DesignAbsorb -DesignPath $designPath -KeepSource:$KeepSource
Complete-Chain
