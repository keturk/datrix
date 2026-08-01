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

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "tasks\plan_waves_multi.py"

# Import shared venv helpers
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

function Invoke-Cleanup {
 Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
  Write-Error "Failed to activate virtual environment"
  exit 1
 }

 $venvPath = Get-DatrixVenvPath
 $PythonExe = Join-Path $venvPath "Scripts\python.exe"

 if (-not (Test-Path $PythonScript)) {
  Write-Error "Python script not found: $PythonScript"
  exit 1
 }

 $pythonArgs = @($PythonScript, $Phases)
 if ($IncludeCompleted) {
  $pythonArgs += "--include-completed"
 }
 if ($BaseDir) {
  $pythonArgs += @("--base-dir", $BaseDir)
 }
 if ($Output) {
  $pythonArgs += @("--output", $Output)
 }
 if ($Dbg) {
  $pythonArgs += "--debug"
 }

 & $PythonExe @pythonArgs
 exit $LASTEXITCODE
} catch {
 Write-Error "Error: $_"
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
