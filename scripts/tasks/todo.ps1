#!/usr/bin/env pwsh
<#
.SYNOPSIS
 List the incomplete tasks and bugs of the workspace, and the stray .tasks folders that listing cannot see.

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.todo. It reads the .tasks and .bugs folders of the workspace root
 and of every datrix and datrix-* repository: a task whose first heading does not start "COMPLETED:" is
 listed (with a warning when its title is missing or not "Task ..." / "<STATUS>: Task ..."), a bug whose
 heading is "Bug ..." is listed, and a phase folder's dependencies.md is listed while the phase has an
 incomplete task. Then every .tasks folder under -BaseDir other than the root's and the repositories' is
 reported: its files are invisible to the listing.

 Exit codes:
   0 = listed
   1 = the base directory does not exist (or a self-test check failed)

.PARAMETER BaseDir
 Workspace root holding .tasks, .bugs and the datrix* repos (default: this workspace).

.PARAMETER Filter
 Only list tasks and bugs whose file name or title contains this text (case-insensitive).

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test over a planted workspace, and the wrapper seam checks.

.EXAMPLE
 .\tasks\todo.ps1 -Filter loader
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ParameterSetName = "Run")][string]$BaseDir,
 [Parameter(Position = 1, ParameterSetName = "Run")][string]$Filter,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.todo" -Parameters $PSBoundParameters
exit $LASTEXITCODE
