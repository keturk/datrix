#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Run prompts one after another as headless Claude Code steps, each slash command on its own
    skill's model.

.DESCRIPTION
    The behaviour is datrix_scripts.skill.skill_chain, over the steps of datrix_scripts.skill.chain.
    A skill invoked from inside another skill runs on the caller's model; only a typed slash
    command switches to the skill's own `model:` and `effort:`. This script types each prompt into
    its own `claude -p` run (on its stdin), so every step gets its skill's model, with the hooks,
    CLAUDE.md and guards of an interactive session. The chain stops at the first step that ends
    in error.

    For a design, use implement-design.ps1, which also checks the result between steps.

    Sessions. By default each step is a FRESH session: it pays the workspace's start-up context
    (about 26k tokens, most of it served from the prompt cache when the model is the same) and
    reads the mandatory docs again. -Resume carries one session through every step instead:
    nothing is re-read, but every turn of every step re-reads the previous steps' whole
    transcript, and a model change writes it to the cache again at the new model's price.

    Every step's stream, JSON result and stderr are kept under <workspace>\.tmp\skill-chain\<timestamp>\.
    Each step prints its models, turns, duration and list-price cost (on a subscription that is
    usage against the plan's limits, not a charge).

    Exit codes: 0 every step finished (or a passing -SelfTest); 1 no prompt was given, the claude
    CLI is not on PATH, a step ended in error, or a self-test check failed; 2 a command line the
    module cannot read.

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

.PARAMETER SelfTest
    Run only the module's self-test (the step command line, the stream and transcript readers,
    the verify and absorb checks, a dry run) and the wrapper seam checks.

.EXAMPLE
    .\skill-chain.ps1 "/fix-codegen-python D:\datrix\datrix-codegen-python\.test_results\test-results-20261005-101500\index.json" "/commit-and-push"
#>
# Steps are the positional arguments ("/a" "/b"): `powershell -File` cannot pass an array to a named
# parameter, so they bind as remaining arguments and no other parameter is positional.
[CmdletBinding(PositionalBinding = $false)]
param(
    [Parameter(ValueFromRemainingArguments = $true)] [string[]]$Step,
    [Parameter()] [switch]$Resume,
    [Parameter()] [ValidateSet("auto", "acceptEdits", "dontAsk", "bypassPermissions")] [string]$PermissionMode,
    [Parameter()] [double]$MaxBudgetUsd,
    [Parameter()] [switch]$DryRun,
    [Parameter()] [switch]$Quiet,
    [Parameter()] [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.skill.skill_chain" -Parameters $PSBoundParameters
exit $LASTEXITCODE
