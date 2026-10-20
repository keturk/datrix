#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List the task artifacts of the workspace's .tasks folders; with -Force, delete them after a yes/no confirmation.

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.cleanup. It reads the workspace root's .tasks and every datrix and
 datrix-* repository's .tasks, and lists each file named task-* or dependencies.md at any depth of them.
 With -Force it asks "Are you sure? {yes/no}", then deletes those files and every folder of each .tasks
 tree they leave empty; an end of input answers no. Nothing at or above the base directory is removed,
 and no symbolic link or junction is entered.

 Exit codes:
   0 = listed, deleted or cancelled
   1 = the base directory does not exist (or a self-test check failed)

.PARAMETER BaseDir
 Workspace root holding .tasks and the datrix* repos (default: this workspace).

.PARAMETER Force
 Delete the listed artifacts, and the folders they leave empty, after confirmation.

.PARAMETER Phase
 Only the artifacts of phases before this number (-Phase 60 deletes phases 1..59).

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test over a planted workspace, and the wrapper seam checks.

.EXAMPLE
 .\tasks\cleanup.ps1 -Force -Phase 60
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ParameterSetName = "Run")][string]$BaseDir,
 [Parameter(ParameterSetName = "Run")][switch]$Force,
 [Parameter(Position = 1, ParameterSetName = "Run")][int]$Phase,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.cleanup" -Parameters $PSBoundParameters
exit $LASTEXITCODE
