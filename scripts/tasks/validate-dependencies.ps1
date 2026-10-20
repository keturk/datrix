#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Validate a phase's dependencies.md against the task files on disk, or print the next free task number.

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.validate_dependencies. Mode A (default) runs the named checks
 (dependencies.md exists, is JSON, lists every task, every dependency id resolves, the graph is acyclic,
 the doc agrees with the task files, task paths are absolute and present, task numbers are unique and
 sequential, provenance), writes them as JSON and prints PASS or FAIL. Mode B (-NextTaskNumber) prints
 only the next free two-digit task number of the phase.

 Exit codes:
   0 = pass (warnings and infos allowed), or the next number was printed
   1 = a check failed (or a self-test check failed)
   2 = usage error (no phase, no such base directory, no task file, or the dependency-id parsing self-check failed)

.PARAMETER Phase
 Phase number (e.g. 31). Required.

.PARAMETER NextTaskNumber
 Print only the next free two-digit task number and exit.

.PARAMETER BaseDir
 Workspace root containing the datrix* repos (default: this workspace).

.PARAMETER Output
 Output JSON path (default: <workspace>\.tmp\tasks\phase-NN-validation.json).

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test over planted phases, and the wrapper seam checks.

.EXAMPLE
 .\tasks\validate-dependencies.ps1 -Phase 31 -NextTaskNumber
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Mandatory = $true, Position = 0, ParameterSetName = "Run")][int]$Phase,
 [Parameter(ParameterSetName = "Run")][switch]$NextTaskNumber,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.validate_dependencies" -Parameters $PSBoundParameters
exit $LASTEXITCODE
