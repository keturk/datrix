# Plan dependency-ordered execution waves for a phase's tasks (Kahn sort +
# quality-gate-last ordering + same-file conflict splitting + blocker detection).
# Usage: .\scripts\tasks\plan-waves.ps1 <phase> [-IncludeCompleted] [-BaseDir <dir>] [-Output <file>] [-Dbg]

[CmdletBinding()]
param(
 [Parameter(Mandatory=$true, Position=0)]
 [int]$Phase,
 [switch]$IncludeCompleted,
 [string]$BaseDir,
 [string]$Output,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @("$Phase")
if ($IncludeCompleted) { $pythonArgs += "--include-completed" }
if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }
if ($Output) { $pythonArgs += @("--output", $Output) }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\plan_waves.py") -Arguments $pythonArgs)
