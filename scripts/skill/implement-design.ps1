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
      implement  /implement-design-direct on its model, one fresh session per piece: STOP AFTER: plan
                 (its Steps 1-2), UNIT: <id> for each ledger unit
      verify     /verify-implementation, TASKS: none, FILES from the ledger, on its model
      absorb     /absorb-design, on its model

    The implement step keeps its work plan in a ledger the script names:
    <workspace>\.tmp\implement-direct-<design file name>.md. The checks between steps are done by
    the script, not by a model:
      * the plan session runs only when there is no ledger (or verify left gaps). No ledger after it
        means it stopped at its gate for a decision (exit 2). Each unchecked unit then gets its own
        session (up to -MaxRounds sessions per unit); every response re-reads the whole context, so
        short sessions cost far less than one long one. Implement is done only when the ledger
        has no unchecked unit and a "## Files changed" section.
      * before each unit session, a fresh interpreter loads every registered plugin. A failure
        (another session's half-finished edit, say) stops the chain with 1 and prints the end of the
        error; rerun once it loads, and the run resumes at the first unchecked unit.
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

.PARAMETER All
    Implement every design of a folder, in name order, with no count cap: <workspace>\design, or the folder
    given as -Design. The first one that does not finish stops the run. Not with -Count.

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
    How many sessions one unit, and how many verify runs, may take before the chain
    gives up. Default: 3.

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
    .\implement-design.ps1 -All

.EXAMPLE
    .\implement-design.ps1 -Design "D:\datrix\design\<the design>.md"

.EXAMPLE
    .\implement-design.ps1 -Design "D:\datrix\design\<the design>.md" -StartAt verify
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)] [string]$Design,
    [int]$Count,
    [switch]$All,
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
