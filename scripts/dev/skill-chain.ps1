#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run skills one after another as headless Claude Code steps, each on its own model.

.DESCRIPTION
    A skill invoked from inside another skill runs on the caller's model; only a typed slash
    command switches to the skill's own `model:` and `effort:`. This script types each step's slash
    command into its own `claude -p` run, so every step gets its skill's model -- /operationalize-design
    and /task-orchestrator on what their frontmatter says, /verify-implementation and /absorb-design on
    theirs -- with the hooks, CLAUDE.md and guards of an interactive session.

    Two forms:
      -Design <path>   the /implement-design tasks path: operationalize -> orchestrate -> verify ->
                       absorb, with the checks between steps done by scripts, not by a model:
                         * operationalize must create a new phase (latest-phase.ps1 before/after);
                           when it does not, it stopped for a decision: the script prints its reply
                           and the session id to answer it in, and stops.
                         * the phase is closed only when phase-status.ps1 shows every task completed
                           with no How-Solved red flag and the design's Status line reads
                           Implemented; otherwise the orchestrator runs again (up to -MaxRounds).
                         * absorb runs only after verify replies "Design conformance: PROVEN"; on
                           INCOMPLETE the orchestrator and verify run again (up to -MaxRounds).
                       The direct path (no tasks) is /implement-design-direct, typed in one session.
      "<prompt>" ...   any sequence of prompts, given as the positional arguments (typically slash commands), run in order; the chain
                       stops at the first step that ends in error.

    Sessions. By default each step is a FRESH session: it pays the workspace's start-up context
    (about 26k tokens, most of it served from the prompt cache when the model is the same) and
    reads the mandatory docs again, and it starts with its whole context window free. -Resume
    carries one session through every step instead: nothing is re-read, but every step starts with
    the previous steps' whole transcript, which on a model change is written to the cache again at
    the new model's price, and which the steps hand over through files (tasks, reports) anyway.

    Every step's JSON result and stderr are kept under <workspace>\.tmp\skill-chain\<timestamp>\.
    Each step prints its models, turns, duration and list-price cost (on a subscription that is
    usage against the plan's limits, not a charge).

    Exit codes:
      0 = every step finished (for -Design: the design is absorbed)
      1 = a step ended in error, or a check between steps failed (the message says which)
      2 = a step stopped for a decision only Jon can make (its reply and session id are printed)

.PARAMETER Design
    The design document to implement, operationalize through absorb.

.PARAMETER StartAt
    With -Design: the step to start at (operationalize | orchestrate | verify | absorb), to resume
    a chain after answering a question. Every step after operationalize needs -Phase.

.PARAMETER Phase
    With -Design and -StartAt after operationalize: the phase the design was operationalized into.

.PARAMETER KeepSource
    With -Design: pass KEEP SOURCE: true to /absorb-design.

.PARAMETER Step
    The prompts to run in order, as the positional arguments (for example "/fix-codegen-python
    <index.json>" "/commit-and-push").

.PARAMETER Resume
    Carry one session through every step instead of a fresh session per step.

.PARAMETER PermissionMode
    The permission mode of every step. Default: auto (the same classifier-approved mode as an
    interactive auto session). The guards run in every mode.

.PARAMETER MaxBudgetUsd
    Stop a step that passes this list-price cost. Default: no cap.

.PARAMETER MaxRounds
    With -Design: how many times the orchestrator (and verify) may run before the chain gives up.
    Default: 3.

.PARAMETER DryRun
    Print the steps that would run, and run none.

.EXAMPLE
    .\skill-chain.ps1 -Design "D:\datrix\design\<the design>.md"

.EXAMPLE
    .\skill-chain.ps1 -Design "D:\datrix\design\<the design>.md" -StartAt orchestrate -Phase 52

.EXAMPLE
    .\skill-chain.ps1 "/fix-codegen-python D:\datrix\datrix-codegen-python\.test_results\test-results-20261005-101500\index.json" "/commit-and-push"
#>

# Steps are the positional arguments ("/a" "/b"): `powershell -File` cannot pass an array to a named
# parameter, and remaining-argument binding happens before a parameter set is chosen, so there are no
# sets and no other positional parameter; -Design and the steps are checked by hand below.
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter()] [string]$Design = "",
    [Parameter()] [ValidateSet("operationalize", "orchestrate", "verify", "absorb")] [string]$StartAt = "operationalize",
    [Parameter()] [int]$Phase = 0,
    [Parameter()] [switch]$KeepSource,
    [Parameter(ValueFromRemainingArguments = $true)] [string[]]$Step = @(),
    [Parameter()] [switch]$Resume,
    [Parameter()] [ValidateSet("auto", "acceptEdits", "dontAsk", "bypassPermissions")] [string]$PermissionMode = "auto",
    [Parameter()] [double]$MaxBudgetUsd = 0,
    [Parameter()] [int]$MaxRounds = 3,
    [Parameter()] [switch]$DryRun
)

$ErrorActionPreference = "Stop"

$scriptsDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$workspace = Split-Path -Parent (Split-Path -Parent $scriptsDir)
$latestPhaseScript = Join-Path $scriptsDir "tasks\latest-phase.ps1"
$phaseStatusScript = Join-Path $scriptsDir "tasks\phase-status.ps1"
$runDir = Join-Path $workspace (".tmp\skill-chain\" + (Get-Date -Format "yyyyMMdd-HHmmss"))
$ProvenPattern = "Design conformance:\W*PROVEN"
$IncompletePattern = "Design conformance:\W*INCOMPLETE"
$ImplementedPattern = "(?m)^\W*Status:\W*Implemented"

$script:SessionId = ""
$script:StepNumber = 0
$script:Steps = New-Object System.Collections.Generic.List[object]

if (-not (Get-Command claude -ErrorAction SilentlyContinue)) {
    Write-Host "The claude CLI is not on PATH. Install it: npm install -g @anthropic-ai/claude-code" -ForegroundColor Red
    exit 1
}

function Invoke-ChainStep {
    param([string]$Name, [string]$Prompt)
    $script:StepNumber += 1
    $label = "{0:D2}-{1}" -f $script:StepNumber, $Name
    Write-Host ""
    Write-Host "=== step $label ===" -ForegroundColor Cyan
    Write-Host $Prompt
    if ($DryRun) {
        return [pscustomobject]@{ Name = $label; IsError = $false; Result = ""; SessionId = ""; DryRun = $true }
    }
    New-Item -ItemType Directory -Force -Path $runDir | Out-Null
    $cliArgs = @("-p", $Prompt, "--output-format", "json", "--permission-mode", $PermissionMode)
    if ($Resume -and $script:SessionId) { $cliArgs += @("--resume", $script:SessionId) }
    if ($MaxBudgetUsd -gt 0) { $cliArgs += @("--max-budget-usd", "$MaxBudgetUsd") }
    $jsonPath = Join-Path $runDir "$label.json"
    $errPath = Join-Path $runDir "$label.stderr.txt"
    $started = Get-Date
    Push-Location $workspace
    try {
        $raw = $null | & claude @cliArgs 2> $errPath
    } finally {
        Pop-Location
    }
    $text = ($raw | Out-String)
    [System.IO.File]::WriteAllText($jsonPath, $text, [System.Text.UTF8Encoding]::new($false))
    try {
        $result = $text | ConvertFrom-Json
    } catch {
        Write-Host "Step $label printed no JSON result (see $jsonPath and $errPath)." -ForegroundColor Red
        return [pscustomobject]@{ Name = $label; IsError = $true; Result = ""; SessionId = ""; DryRun = $false }
    }
    if ($result.session_id) { $script:SessionId = $result.session_id }
    $models = @($result.modelUsage.PSObject.Properties | ForEach-Object { $_.Name }) -join ", "
    $minutes = [math]::Round(((Get-Date) - $started).TotalMinutes, 1)
    $denials = @($result.permission_denials).Count
    $row = [pscustomobject]@{
        Name = $label; IsError = [bool]$result.is_error; Subtype = $result.subtype; Result = [string]$result.result
        SessionId = $result.session_id; Models = $models; Turns = $result.num_turns; Minutes = $minutes
        CostUsd = [math]::Round([double]$result.total_cost_usd, 2); Denials = $denials; DryRun = $false
    }
    $script:Steps.Add($row)
    $colour = if ($row.IsError) { "Red" } else { "Green" }
    Write-Host ("{0}: {1}; models {2}; {3} turns; {4} min; list cost {5} USD; {6} permission denial(s); session {7}" -f `
        $label, $(if ($row.IsError) { "ERROR ($($row.Subtype))" } else { "done" }), $models, $row.Turns, $minutes,
        $row.CostUsd, $denials, $row.SessionId) -ForegroundColor $colour
    return $row
}

function Write-Tail {
    param([string]$Text, [int]$Lines = 25)
    $all = $Text -split "`r?`n"
    $all[[math]::Max(0, $all.Count - $Lines)..($all.Count - 1)] | ForEach-Object { Write-Host "  $_" }
}

function Stop-Chain {
    param([int]$Code, [string]$Message, [object]$Row)
    Write-Host ""
    Write-Host $Message -ForegroundColor $(if ($Code -eq 2) { "Yellow" } else { "Red" })
    if ($Row -and $Row.Result) {
        Write-Host "The step's last reply ends:"
        Write-Tail $Row.Result
    }
    if ($Row -and $Row.SessionId) {
        Write-Host "Continue that session interactively: claude --resume $($Row.SessionId)"
    }
    Write-Summary
    exit $Code
}

function Write-Summary {
    if ($script:Steps.Count -eq 0) { return }
    Write-Host ""
    Write-Host "=== chain summary (logs: $runDir) ===" -ForegroundColor Cyan
    $script:Steps | Format-Table Name, Models, Turns, Minutes, CostUsd, Denials, @{ n = "Error"; e = { $_.IsError } } -AutoSize | Out-String | Write-Host
}

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
    if (Test-Path $Design) {
        if (-not ((Get-Content -Raw -Encoding UTF8 $Design) -match $ImplementedPattern)) {
            return "every task of phase $Number is completed, but the design's Status line is not Implemented"
        }
    }
    return ""
}

function Invoke-Orchestration {
    param([int]$Number)
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

function Invoke-DesignChain {
    $designPath = (Resolve-Path $Design).Path
    $order = @("operationalize", "orchestrate", "verify", "absorb")
    $first = [array]::IndexOf($order, $StartAt)
    $number = $Phase
    if ($first -gt 0 -and $number -le 0) {
        Write-Host "-StartAt $StartAt needs -Phase: the phase the design was operationalized into." -ForegroundColor Red
        exit 1
    }

    if ($first -le 0) {
        $before = Get-LatestPhase
        $row = Invoke-ChainStep "operationalize" "/operationalize-design`nDOCUMENT: $designPath"
        if ($row.DryRun) {
            $number = "<the phase operationalize creates>"
        } else {
            if ($row.IsError) { Stop-Chain 1 "/operationalize-design ended in error ($($row.Subtype))." $row }
            $number = Get-LatestPhase
            if ($number -le $before) {
                Stop-Chain 2 ("/operationalize-design created no phase, so it stopped for a decision. Answer it in " +
                    "its session, then rerun with -StartAt orchestrate -Phase <the phase it creates>.") $row
            }
            Write-Host "Operationalized into phase $number." -ForegroundColor Green
        }
    }

    if ($first -le 1) { Invoke-Orchestration $number }

    if ($first -le 2) {
        for ($round = 1; $round -le $MaxRounds; $round++) {
            $row = Invoke-ChainStep "verify" "/verify-implementation`nDESIGN: $designPath`nTASKS: $number"
            if ($row.DryRun) { break }
            if ($row.IsError) { Stop-Chain 1 "/verify-implementation ended in error ($($row.Subtype))." $row }
            if ($row.Result -match $ProvenPattern) { break }
            if (-not ($row.Result -match $IncompletePattern)) {
                Stop-Chain 2 "/verify-implementation replied with neither PROVEN nor INCOMPLETE; read its reply." $row
            }
            if ($round -eq $MaxRounds) {
                Stop-Chain 1 "The design is still INCOMPLETE after $MaxRounds verify round(s); it is not absorbed." $row
            }
            Write-Host "Verify round ${round}: INCOMPLETE. Running the orchestrator on phase $number again." -ForegroundColor Yellow
            Invoke-Orchestration $number
        }
    }

    $keep = if ($KeepSource) { "`nKEEP SOURCE: true" } else { "" }
    $row = Invoke-ChainStep "absorb" "/absorb-design`nDOCUMENT: $designPath$keep"
    if ($row.DryRun) { return }
    if ($row.IsError) { Stop-Chain 1 "/absorb-design ended in error ($($row.Subtype))." $row }
    if (-not $KeepSource -and (Test-Path $designPath)) {
        Stop-Chain 2 "/absorb-design finished but the design still exists, so it stopped at a question; read its reply." $row
    }
}

if ([bool]$Design -eq ($Step.Count -gt 0)) {
    Write-Host 'Pass exactly one of -Design <path> or the prompts to run ("/a" "/b" ...). Get-Help .\skill-chain.ps1 -Full.' -ForegroundColor Red
    exit 1
}
if ($Design) {
    if (-not (Test-Path $Design)) {
        Write-Host "Design document not found: $Design" -ForegroundColor Red
        exit 1
    }
    Invoke-DesignChain
} else {
    $index = 0
    foreach ($prompt in $Step) {
        $index += 1
        $row = Invoke-ChainStep "step$index" $prompt
        if (-not $row.DryRun -and $row.IsError) { Stop-Chain 1 "Step $index ended in error ($($row.Subtype))." $row }
    }
}

Write-Summary
exit 0
