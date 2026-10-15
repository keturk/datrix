# Give tasks written before the ## Orientation block existed one, deterministically (no writer, no model):
# review-list Python files the task does not edit become exact `outline:` entries, unique cited functions
# become `symbol:` entries (see tasks/lib/retrofit_orientation.py). Dry run unless -Apply.
# Usage: .\scripts\tasks\retrofit-orientation.ps1 [-Task <file>[,<file>...]] [-Phase <NN>] [-Apply] [-BaseDir <dir>]

[CmdletBinding()]
param(
 [string[]]$Task = @(),
 [int]$Phase = -1,
 [switch]$Apply,
 [string]$BaseDir
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @($Task)
if ($Phase -ge 0) { $pythonArgs += @("--phase", "$Phase") }
if ($Apply) { $pythonArgs += "--apply" }
if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\retrofit_orientation.py") -Arguments $pythonArgs)
