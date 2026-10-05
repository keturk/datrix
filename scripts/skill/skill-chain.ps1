#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run prompts one after another as headless Claude Code steps, each slash command on its own
    skill's model.

.DESCRIPTION
    A skill invoked from inside another skill runs on the caller's model; only a typed slash
    command switches to the skill's own `model:` and `effort:`. This script types each prompt into
    its own `claude -p` run, so every step gets its skill's model, with the hooks, CLAUDE.md and
    guards of an interactive session. The chain stops at the first step that ends in error.

    For a design, use the scripts that also check the result between steps:
    implement-design.ps1 (tasks path) and implement-design-direct.ps1 (direct path).

    Sessions. By default each step is a FRESH session: it pays the workspace's start-up context
    (about 26k tokens, most of it served from the prompt cache when the model is the same) and
    reads the mandatory docs again. -Resume carries one session through every step instead:
    nothing is re-read, but every turn of every step re-reads the previous steps' whole
    transcript, and a model change writes it to the cache again at the new model's price.

    Every step's JSON result and stderr are kept under <workspace>\.tmp\skill-chain\<timestamp>\.
    Each step prints its models, turns, duration and list-price cost (on a subscription that is
    usage against the plan's limits, not a charge).

    Exit codes: 0 every step finished; 1 a step ended in error.

.PARAMETER Step
    The prompts to run in order, as the positional arguments (for example "/fix-codegen-python
    <index.json>" "/commit-and-push").

.PARAMETER Resume
    Carry one session through every step instead of a fresh session per step.

.PARAMETER PermissionMode
    The permission mode of every step. Default: auto. The guards run in every mode.

.PARAMETER MaxBudgetUsd
    Stop a step that passes this list-price cost. Default: no cap.

.PARAMETER Quiet
    Show only each step's prompt and summary line. By default every agent message, tool call
    and refused tool call is printed as it happens.

.PARAMETER DryRun
    Print the steps that would run, and run none.

.EXAMPLE
    .\skill-chain.ps1 "/fix-codegen-python D:\datrix\datrix-codegen-python\.test_results\test-results-20261005-101500\index.json" "/commit-and-push"
#>
# Steps are the positional arguments ("/a" "/b"): `powershell -File` cannot pass an array to a named
# parameter, so they bind as remaining arguments and no other parameter is positional.
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)] [string[]]$Step = @(),
    [Parameter()] [switch]$Resume,
    [Parameter()] [ValidateSet("auto", "acceptEdits", "dontAsk", "bypassPermissions")] [string]$PermissionMode = "auto",
    [Parameter()] [double]$MaxBudgetUsd = 0,
    [Parameter()] [switch]$DryRun,
    [Parameter()] [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$scriptsDir = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)
$workspace = Split-Path -Parent (Split-Path -Parent $scriptsDir)
Import-Module (Join-Path $scriptsDir "skill\SkillChain.psm1") -Force

if ($Step.Count -eq 0) {
    Write-Host 'Pass the prompts to run ("/a" "/b" ...). For a design: implement-design.ps1 or implement-design-direct.ps1.' -ForegroundColor Red
    exit 1
}

Initialize-SkillChain -Workspace $workspace -Resume:$Resume -PermissionMode $PermissionMode -MaxBudgetUsd $MaxBudgetUsd -DryRun:$DryRun -Quiet:$Quiet

$index = 0
foreach ($prompt in $Step) {
    $index += 1
    $row = Invoke-ChainStep "step$index" $prompt
    if (-not $row.DryRun -and $row.IsError) { Stop-Chain 1 "Step $index ended in error ($($row.Subtype))." $row }
}
Complete-Chain
