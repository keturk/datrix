#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Plan dependency-ordered execution waves for SEVERAL phases run as one batch.

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.plan_waves_multi: plan-waves' Kahn sort, quality-gate-last
 ordering, same-file conflict splitting and blocker detection over the tasks of every phase named,
 with a dependency into another batched phase planned as an ordinary edge, plus the phase-order
 repair for two phases' tasks writing the same file. Writes the plan as JSON and prints a summary.

 Exit codes:
   0 = planned with no blocker
   1 = a blocker, a cycle, an unschedulable task or a residual file conflict (or a self-test check failed)
   2 = usage error (no phases, fewer than two, no such base directory, or no task file)

.PARAMETER Phases
 A range (5-8), a comma list (5,6,7,8), or a mix (5-6,8). Required.

.PARAMETER IncludeCompleted
 Plan every task, not just the non-completed ones.

.PARAMETER BaseDir
 Workspace root containing the datrix* repos (default: this workspace).

.PARAMETER Output
 Output JSON path (default: <workspace>\.tmp\tasks\phases-NN-MM-waves.json).

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test over two planted phases, and the wrapper seam checks.

.EXAMPLE
 .\tasks\plan-waves-multi.ps1 5-8
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Mandatory = $true, Position = 0, ParameterSetName = "Run")][string]$Phases,
 [Parameter(ParameterSetName = "Run")][switch]$IncludeCompleted,
 [Parameter(ParameterSetName = "Run")][string]$BaseDir,
 [Parameter(ParameterSetName = "Run")][string]$Output,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.plan_waves_multi" -Parameters $PSBoundParameters
exit $LASTEXITCODE
