# Validate a phase's dependencies.md against the task files on disk
# (Mode A), or print only the next free task number (-NextTaskNumber, Mode B).
# Usage: .\scripts\tasks\validate-dependencies.ps1 -Phase <NN> [-NextTaskNumber] [-BaseDir <dir>] [-Output <file>] [-Dbg]

[CmdletBinding()]
param(
 [Parameter(Mandatory=$true, Position=0)]
 [int]$Phase,
 [switch]$NextTaskNumber,
 [string]$BaseDir,
 [string]$Output,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @("--phase", "$Phase")
if ($NextTaskNumber) { $pythonArgs += "--next-task-number" }
if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }
if ($Output) { $pythonArgs += @("--output", $Output) }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\validate_dependencies.py") -Arguments $pythonArgs)
