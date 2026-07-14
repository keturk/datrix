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

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
$PythonScript = Join-Path $libraryDir "tasks\validate_dependencies.py"

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

 $pythonArgs = @($PythonScript, "--phase", $Phase)
 if ($NextTaskNumber) {
  $pythonArgs += "--next-task-number"
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
