#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Build the apply-reviews worklist for a phase.

.DESCRIPTION
 The behaviour is datrix_scripts.review.apply_reviews_prep: discover the phase's Tier 1/Tier 2
 review artifacts, drop already-applied findings, and group the rest by target sorted by
 severity. The worklist JSON carries everything; the console prints one summary line and its
 path. Review artifacts and task files are data, never modified.

 Exit codes: 0 = worklist written, 2 = usage (no phase, a missing base directory, or a malformed
 review artifact or applied marker).

.PARAMETER Phase
 Phase number (e.g. 31). Positional.

.PARAMETER Source
 Which review tier(s) to include: local, phase or all (default: all).

.PARAMETER BaseDir
 Workspace root containing the datrix* repos (default: this workspace).

.PARAMETER Output
 Output JSON path (default: <workspace>\.tmp\review\phase-NN-worklist.json).

.PARAMETER Dbg
 Log at DEBUG level.

.PARAMETER SelfTest
 Run only the module's self-test: a planted phase's worklist drops the applied findings and
 orders the rest by severity, a missing phase or base directory and a malformed artifact are
 refused, and the wrapper seam.

.EXAMPLE
 .\apply-reviews-prep.ps1 -Phase 31

.EXAMPLE
 .\apply-reviews-prep.ps1 -Phase 31 -Source local
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run", Position = 0, Mandatory = $true)][int]$Phase,
 [Parameter(ParameterSetName = "Run")][ValidateSet("local", "phase", "all")][string]$Source,
 [Parameter(ParameterSetName = "Run")][string]$BaseDir,
 [Parameter(ParameterSetName = "Run")][string]$Output,
 [Parameter(ParameterSetName = "Run")][switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.review.apply_reviews_prep" -Parameters $PSBoundParameters
exit $LASTEXITCODE
