# Plan dependency-ordered execution waves for SEVERAL phases run as one batch
# (Kahn sort + quality-gate-last ordering + same-file conflict splitting +
# cross-phase phase-order repair + blocker detection).
# Usage: .\scripts\tasks\plan-waves-multi.ps1 <phases> [-IncludeCompleted] [-BaseDir <dir>] [-Output <file>] [-Dbg]
#   <phases> is a range (5-8), a comma list (5,6,7,8), or a mix (5-6,8).

[CmdletBinding()]
param(
 [Parameter(Mandatory=$true, Position=0)]
 [string]$Phases,
 [switch]$IncludeCompleted,
 [string]$BaseDir,
 [string]$Output,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @($Phases)
if ($IncludeCompleted) { $pythonArgs += "--include-completed" }
if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }
if ($Output) { $pythonArgs += @("--output", $Output) }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\plan_waves_multi.py") -Arguments $pythonArgs)
