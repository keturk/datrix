#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Mark a task markdown file as completed by setting its first heading to "COMPLETED: Task ...".

.DESCRIPTION
 The behaviour is datrix_scripts.tasks.complete. The task reference resolves to exactly one file
 (an absolute path, a path relative to the current directory or the workspace, else a unique file
 name or path suffix under a .tasks folder); its first heading must be "Task ..." or
 "<STATUS>: Task ...". This is the one way a task's status heading changes: the edit hooks refuse
 a Write/Edit that adds a COMPLETED heading to a task file.

 Exit codes:
   0 = marked, or already completed
   1 = not found, ambiguous, not a task title, or not writable
   2 = usage error

.PARAMETER TaskFile
 Task file path (absolute, relative, or task file name). Required.

.PARAMETER Dbg
 Debug logging.

.PARAMETER SelfTest
 Run only the module's self-test: planted task files are marked, refused or found, and the wrapper
 seam holds.

.EXAMPLE
 .\tasks\complete.ps1 <path to the task file>
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Mandatory = $true, Position = 0, ParameterSetName = "Run")][string]$TaskFile,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.tasks.complete" -Parameters $PSBoundParameters
exit $LASTEXITCODE
