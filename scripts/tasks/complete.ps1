# Mark a task markdown file as completed by setting its first heading to "COMPLETED: Task ..."
# Usage: .\scripts\tasks\complete.ps1 <task-file> [-Dbg]

[CmdletBinding()]
param(
 [Parameter(Mandatory=$true, Position=0)]
 [string]$TaskFile,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @($TaskFile)
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\complete.py") -Arguments $pythonArgs)
