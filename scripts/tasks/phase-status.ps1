#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Report per-task status for a phase across all repos.

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.phase_status: parses every task file of the phase in every
 datrix* repo, merges the phase-level dependencies.md (JSON preferred, legacy "Group N" fallback),
 and writes one JSON status document. Prints a one-line summary and the document's path.

 Exit codes:
   0 = written
   1 = a self-test check failed
   2 = usage error (no phase, no such base directory, or no task file in the phase)

.PARAMETER Phase
 Phase number (e.g. 31). Required.

.PARAMETER BaseDir
 Workspace root containing the datrix* repos (default: this workspace).

.PARAMETER Output
 Output JSON path (default: <workspace>\.tmp\tasks\phase-NN-status.json).

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test over a planted phase, and the wrapper seam checks.

.EXAMPLE
 .\tasks\phase-status.ps1 31
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Mandatory = $true, Position = 0, ParameterSetName = "Run")][int]$Phase,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.phase_status" -Parameters $PSBoundParameters
exit $LASTEXITCODE
