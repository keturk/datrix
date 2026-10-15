# Report per-task status for a phase across all repos (parses task files +
# merges the phase-level dependencies.md into one JSON status document).
# Usage: .\scripts\tasks\phase-status.ps1 <phase> [-BaseDir <dir>] [-Output <file>] [-Dbg]

[CmdletBinding()]
param(
 [Parameter(Mandatory=$true, Position=0)]
 [int]$Phase,
 [string]$BaseDir,
 [string]$Output,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @("$Phase")
if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }
if ($Output) { $pythonArgs += @("--output", $Output) }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\phase_status.py") -Arguments $pythonArgs)
