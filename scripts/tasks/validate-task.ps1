# Validate task files against the tree as it is now: the ## Orientation block resolves, and every
# path:line citation still points at what it says (see tasks/lib/validate_task.py).
# Usage: .\scripts\tasks\validate-task.ps1 [-Task <file>[,<file>...]] [-Phase <NN>] [-Strict] [-RequireOrientation] [-BaseDir <dir>]

[CmdletBinding()]
param(
 [string[]]$Task = @(),
 [int]$Phase = -1,
 [switch]$Strict,
 [switch]$RequireOrientation,
 [string]$BaseDir
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @($Task)
if ($Phase -ge 0) { $pythonArgs += @("--phase", "$Phase") }
if ($Strict) { $pythonArgs += "--strict" }
if ($RequireOrientation) { $pythonArgs += "--require-orientation" }
if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\validate_task.py") -Arguments $pythonArgs)
