#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Mechanical service-level scan for the /evaluate-generated-service skill.

.DESCRIPTION
 Parses the service DSL with the real Datrix pipeline and cross-checks ONE
 generated service directory: DSL feature inventory, manifest subset with a
 both-direction filesystem diff, directory-name convention check, per-block /
 per-entity expected-artifact existence table, dead-code candidates, env-var
 references, and Dockerfile / migrations existence. Writes service-scan JSON;
 the console prints a short summary only. Semantic verification stays with
 the model (skill Phase 3.5) — this scan checks existence only.

.PARAMETER Source
 Path to the service .dtrx file, or a system.dtrx combined with -Service.

.PARAMETER Service
 Service name (qualified, simple, or kebab-case). Required when Source
 defines more than one service.

.PARAMETER Generated
 Generated SERVICE directory (the service-specific folder, not the project root).

.PARAMETER ProjectGenerated
 Generated PROJECT root holding .datrix\manifests. Auto-detected from the
 parent directories of -Generated when omitted.

.PARAMETER Output
 Output JSON path. Default: <workspace>\.tmp\eval\<project>\service-<name>-scan.json.

.PARAMETER ConfigProfile
 Config profile the project was generated with (default: test, matching
 generate.ps1's default).

.PARAMETER Dbg
 Enable debug logging in the Python script.

.EXAMPLE
 .\evaluate-service-scan.ps1 -Source examples\01-foundation\system.dtrx -Service BookService -Generated D:\datrix\.generated\python\docker-compose\local\01-foundation\library_book_service
#>

[CmdletBinding()]
param(
 [Parameter(Position=0)]
 [string]$Source,

 [Parameter()]
 [string]$Service = "",

 [Parameter(Position=1)]
 [string]$Generated,

 [Parameter()]
 [string]$ProjectGenerated = "",

 [Parameter()]
 [string]$Output = "",

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
$PythonScript = Join-Path $libraryDir "dev\evaluate_service_scan.py"

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
 if ($Service) {
  $pythonArgs += @("--service", $Service)
 }
 if ($Generated) {
  $pythonArgs += @("--generated", $Generated)
 }
 if ($ProjectGenerated) {
  $pythonArgs += @("--project-generated", $ProjectGenerated)
 }
 if ($Output) {
  $pythonArgs += @("--output", $Output)
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
