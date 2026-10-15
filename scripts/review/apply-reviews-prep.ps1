# Build the apply-reviews worklist for a phase: discover Tier 1/Tier 2 review
# artifacts, drop already-applied findings, group by target sorted by severity.
# Usage: .\scripts\review\apply-reviews-prep.ps1 -Phase <NN> [-Source local|phase|all] [-BaseDir <dir>] [-Output <file>] [-Dbg]

[CmdletBinding()]
param(
 [Parameter(Mandatory=$true, Position=0)]
 [int]$Phase,
 [ValidateSet("local", "phase", "all")]
 [string]$Source = "all",
 [string]$BaseDir,
 [string]$Output,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @("--phase", $Phase, "--source", $Source)
if ($BaseDir) {
 $pythonArgs += @("--base-dir", $BaseDir)
}
if ($Output) {
 $pythonArgs += @("--output", $Output)
}
if ($Dbg) {
 $pythonArgs += "--debug"
}
exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\apply_reviews_prep.py") -Arguments $pythonArgs -ShowCommand:$Dbg)
