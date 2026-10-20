#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Plan dependency-ordered execution waves for a phase's tasks.

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.plan_waves: a Kahn sort over the tasks' Depends on graph,
 quality gates ordered last, waves split where two tasks touch the same file, and blocker
 detection (missing dependency file, unmet cross-phase dependency, a task mixing languages, a
 dependencies.md that disagrees with the task files). Writes the plan as JSON and prints a summary.

 Exit codes:
   0 = planned with no blocker
   1 = a blocker, a dependency cycle or an unschedulable task (or a self-test check failed)
   2 = usage error (no phase, no such base directory, no task file in the phase, duplicate task id)

.PARAMETER Phase
 Phase number (e.g. 31). Required.

.PARAMETER IncludeCompleted
 Plan every task, not just the non-completed ones.

.PARAMETER BaseDir
 Workspace root containing the datrix* repos (default: this workspace).

.PARAMETER Output
 Output JSON path (default: <workspace>\.tmp\tasks\phase-NN-waves.json).

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test over a planted phase, and the wrapper seam checks.

.EXAMPLE
 .\tasks\plan-waves.ps1 31 -IncludeCompleted
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Mandatory = $true, Position = 0, ParameterSetName = "Run")][int]$Phase,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.plan_waves" -Parameters $PSBoundParameters
exit $LASTEXITCODE
