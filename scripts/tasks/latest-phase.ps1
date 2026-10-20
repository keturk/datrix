#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Print the highest phase number of the workspace's .tasks folders.

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.latest_phase. It reads the phase-<number> folders of the
 workspace root's .tasks and of every datrix and datrix-* repository's .tasks, and prints only the
 highest number (31, not phase-31), for use in scripts; nothing when there is no phase folder.

 Exit codes:
   0 = done (a phase found or not)
   1 = the base directory does not exist (or a self-test check failed)

.PARAMETER BaseDir
 Workspace root holding .tasks and the datrix* repos (default: this workspace).

.PARAMETER Dbg
 Print every phase number found and the latest, instead of the number alone.

.PARAMETER SelfTest
 Run only the module's self-test over planted folders, and the wrapper seam checks.

.EXAMPLE
 .\tasks\latest-phase.ps1
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ParameterSetName = "Run")][string]$BaseDir,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.latest_phase" -Parameters $PSBoundParameters
exit $LASTEXITCODE
