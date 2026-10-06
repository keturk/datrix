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

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$PythonScript = Join-Path $ScriptDir "lib\retrofit_orientation.py"

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
 if ($Apply) {
  $pythonArgs += "--apply"
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
