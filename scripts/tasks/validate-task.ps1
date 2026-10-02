# Validate task files against the tree as it is now: the ## Orientation block resolves, and every
# path:line citation still points at what it says (see library/tasks/validate_task.py).
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

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "tasks\validate_task.py"

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

 $pythonArgs = @($PythonScript)
 foreach ($file in $Task) {
  $pythonArgs += $file
 }
 if ($Phase -ge 0) {
  $pythonArgs += @("--phase", $Phase)
 }
 if ($Strict) {
  $pythonArgs += "--strict"
 }
 if ($RequireOrientation) {
  $pythonArgs += "--require-orientation"
 }
 if ($BaseDir) {
  $pythonArgs += @("--base-dir", $BaseDir)
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
