#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Pull repositories over uncommitted local work: the mechanical half of /resolve-conflicts.

.DESCRIPTION
    Wraps scripts\git\lib\resolve_pull.py. Per repository whose upstream is ahead: measures the
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
      0 = every repository up to date or finished
      1 = at least one needs a hand merge, has a conflict already in progress, or failed
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

.EXAMPLE
    .\resolve-pull.ps1 datrix-common datrix-codegen-python

.EXAMPLE
    .\resolve-pull.ps1 datrix-common -Finish
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)] [string[]]$Repo = @(),
    [Parameter()] [switch]$Finish,
    [Parameter()] [string[]]$Merged = @(),
    [Parameter()] [switch]$NoModel,
    [Parameter()] [string[]]$LocalMachines = @(),
    [Parameter()] [string[]]$LlmModel = @(),
    [Parameter()] [int]$LlmTimeout = 300
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @($Repo)
if ($Finish) { $pyArgs += "--finish" }
if ($Merged.Count -gt 0) { $pyArgs += @("--merged") + $Merged }
if ($NoModel) { $pyArgs += "--no-model" }
$pyArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\resolve_pull.py") -Arguments $pyArgs)
