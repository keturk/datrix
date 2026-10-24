#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Implement a design directly, with no tasks: implement -> verify -> absorb, each step a fresh
    headless session on its own skill's model.

.DESCRIPTION
    The behaviour is datrix_scripts.skill.implement_design, over the steps of
    datrix_scripts.skill.chain. The script form of /implement-design-direct. Typed in one session,
    that skill runs verify and absorb on its own model, because a skill invoked from another skill
    runs on the caller's; here each step is typed into its own `claude -p` run (on its stdin):
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
      * absorb runs only after verify replies "Design conformance: PROVEN". That reply is kept at
        <workspace>\.tmp\verify-proven-<design file name>.md and passed to absorb as VERIFIED, its
        licence to delete the design; -StartAt absorb needs that file from an earlier run. On
        INCOMPLETE, verify's reply is saved and implement runs again with GAPS: <that file>, then
        verify again (up to -MaxRounds).

    Every step's stream, JSON result and stderr are kept under <workspace>\.tmp\skill-chain\<timestamp>\.
    Exit codes: 0 the design is absorbed (or a passing -SelfTest); 1 a step ended in error, a check
    failed, or no usable design or ledger was given; 2 a step stopped for a decision only Jon can
    make (its reply and session id are printed), or a command line the module cannot read.

.PARAMETER Design
    The design document to implement. Without it, the first -Count design documents of
    <workspace>\design are implemented in name order; the first one that does not finish stops the run.

.PARAMETER Count
    How many designs to take from <workspace>\design, first by name. Default: 10. Not used with -Design.

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

.PARAMETER SelfTest
    Run only the module's self-test (the chain checks, the ledger checks, a dry run) and the
    wrapper seam checks.

.EXAMPLE
    .\implement-design.ps1 -Count 3 -DryRun

.EXAMPLE
    .\implement-design.ps1 -Design "D:\datrix\design\<the design>.md"

.EXAMPLE
    .\implement-design.ps1 -Design "D:\datrix\design\<the design>.md" -StartAt verify
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string]$Design,
    [int]$Count,
    [ValidateSet("implement", "verify", "absorb")] [string]$StartAt,
    [switch]$KeepSource,
    [switch]$Resume,
    [ValidateSet("auto", "acceptEdits", "dontAsk", "bypassPermissions")] [string]$PermissionMode,
    [double]$MaxBudgetUsd,
    [int]$MaxRounds,
    [switch]$DryRun,
    [switch]$Quiet,
    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.skill.implement_design" -Parameters $PSBoundParameters
exit $LASTEXITCODE
