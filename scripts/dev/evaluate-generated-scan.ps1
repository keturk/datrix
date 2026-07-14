#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Mechanical project-level scan for the /evaluate-generated skill (quick mode).

.DESCRIPTION
 Parses the system.dtrx with the real Datrix pipeline, cross-checks the
 generated project (service directories, manifests, infrastructure files,
 docker-compose entries), rolls up critical blockers and warnings, and writes
 project-scan.json plus one service-*.prompt.md per service into the
 evaluation directory. All detail goes to the output files; the console
 prints a short summary only.

.PARAMETER Source
 Path to the system.dtrx file.

.PARAMETER Generated
 Generated project root directory (as produced by generate.ps1).

.PARAMETER EvalDir
 Evaluation output directory. Default: <workspace>\.tmp\eval\<project-slug>\.

.PARAMETER ConfigProfile
 Config profile the project was generated with (default: test, matching
 generate.ps1's default).

.PARAMETER Dbg
 Enable debug logging in the Python script.

.EXAMPLE
 .\evaluate-generated-scan.ps1 -Source examples\01-foundation\system.dtrx -Generated D:\datrix\.generated\python\docker-compose\local\01-foundation
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Source,

 [Parameter(Position=1)]
 [string]$Generated,

 [Parameter()]
 [string]$EvalDir = "",

 [Parameter()]
 [string]$ConfigProfile = "",

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Get the directory where this script is located
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\library"
# Path to the Python script
$PythonScript = Join-Path $libraryDir "dev\evaluate_generated_scan.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $ScriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Function to handle cleanup on exit
function Invoke-Cleanup {
 Disable-DatrixVenv
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
 # Ensure virtual environment is activated
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
  Write-Error "Failed to activate virtual environment"
  exit 1
 }

 # Get Python executable from venv
 $venvPath = Get-DatrixVenvPath
 $PythonExe = Join-Path $venvPath "Scripts\python.exe"

 if (-not (Test-Path $PythonScript)) {
  Write-Error "Python script not found: $PythonScript"
  exit 1
 }

 # Build arguments for Python script
 $pythonArgs = @($PythonScript)
 if ($Source) {
  $pythonArgs += @("--source", $Source)
 }
 if ($Generated) {
  $pythonArgs += @("--generated", $Generated)
 }
 if ($EvalDir) {
  $pythonArgs += @("--eval-dir", $EvalDir)
 }
 if ($ConfigProfile) {
  $pythonArgs += @("--profile", $ConfigProfile)
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
