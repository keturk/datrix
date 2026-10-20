#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pull repositories over uncommitted local work: the mechanical half of /resolve-conflicts.

.DESCRIPTION
    The behaviour is datrix_scripts.git.resolve_pull. Per repository whose upstream is ahead: measures the
    tracked overlap and the untracked collisions, restores line endings on paths whose only local
    difference is line endings, shelves ONLY the overlapping paths (path-limited stash), sets aside
    untracked collisions, pulls (--ff-only, or --no-rebase --no-edit when diverged), reapplies with
    `stash apply`, verifies, and drops the stash entry.

    A conflict stops there with the markers in place and a packet at
    <workspace>\.tmp\resolve-conflicts\<repo>\conflicts.md: each conflict hunk's local, base and
    incoming text, with a local model's merge draft checked against both sides (a lead). Merge by
    hand with Edit, then run again with -Finish: it checks for markers, unstages the shelved paths,
    proves every local added line is in the working tree, and only then drops the stash entry.

    Nothing here discards work. The agent guard allows it only once Jon has typed
    /resolve-conflicts in the session; Jon may run it in his own terminal at any time.

    Exit codes:
      0 = every repository up to date or finished (or a passing -SelfTest)
      1 = at least one needs a hand merge, has a conflict already in progress, or failed
          (or a self-test check failed)
      2 = the run could not start

.PARAMETER Repo
    Repository names. Omit for every git repository in the workspace.

.PARAMETER Finish
    Verify the hand merge and drop the stash entry.

.PARAMETER Merged
    With -Finish: paths whose local lines were deliberately merged with the incoming change; a local
    line missing from them is reported instead of refused.

.PARAMETER NoModel
    No local-model merge drafts in the conflict packet.

.PARAMETER LocalMachines
    Machines to search for model servers, in preference order. Omit for the default list in
    common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
    Models to use, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
    Request timeout in seconds. Default: 300.

.PARAMETER SelfTest
    Run only the wrapper seam checks: the wrapper and its twin are the templates rendered with
    exactly the module's options.

.EXAMPLE
    .\git\resolve-pull.ps1 datrix-common datrix-codegen-python

.EXAMPLE
    .\git\resolve-pull.ps1 datrix-common -Finish
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$Repo,
 [Parameter(ParameterSetName = "Run")][switch]$Finish,
 [Parameter(ParameterSetName = "Run")][string[]]$Merged,
 [Parameter(ParameterSetName = "Run")][switch]$NoModel,
 [Parameter(ParameterSetName = "Run")][string[]]$LocalMachines,
 [Parameter(ParameterSetName = "Run")][string[]]$LlmModel,
 [Parameter(ParameterSetName = "Run")][int]$LlmTimeout = 300,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.git.resolve_pull" -Parameters $PSBoundParameters
exit $LASTEXITCODE
