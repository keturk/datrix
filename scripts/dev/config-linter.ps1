#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Lint and format ConfigDSL (.dcfg) files.

.DESCRIPTION
 Discovers .dcfg files and applies deterministic formatting.
 Also reports syntax errors and simple style warnings.

.PARAMETER Path
 File or directory paths to scan (default: all datrix repositories).

.PARAMETER Check
 Check mode only. Reports issues and needed formatting without writing files.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\config-linter.ps1
 Format all .dcfg files under all datrix repositories.

.EXAMPLE
 .\config-linter.ps1 -Check
 Check all .dcfg files without modifying files.

.EXAMPLE
 .\config-linter.ps1 examples\01-foundation\config
 Format .dcfg files only in the provided folder.
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Path = @(),

 [Parameter()]
 [switch]$Check,

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\config_linter.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: config_linter.py not found at: $pythonScript"
 exit 1
}

function Invoke-Cleanup {
 Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

trap {
 Write-Host ""
 Write-Warning "Interrupted by user (Ctrl-C)"
 Invoke-Cleanup
 exit 130
}

try {
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
  Write-Error "Failed to activate virtual environment"
  exit 1
 }

 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"

 $pathsToCheck = @()
 if ($Path.Count -eq 0) {
  $directories = Get-DatrixDirectoryPaths
  foreach ($dirPath in $directories) {
   if (Test-Path $dirPath) {
    $pathsToCheck += $dirPath
   }
  }
 } else {
  $pathsToCheck = $Path
 }

 $pythonArgs = @($pythonScript) + $pathsToCheck
 if ($Check) {
  $pythonArgs += "--check"
 }
 if ($Dbg) {
  $pythonArgs += "--debug"
 }

 Write-Host "Running config linter..." -ForegroundColor Cyan
 Write-Host ""

 & $pythonExe @pythonArgs
 $exitCode = $LASTEXITCODE

 exit $exitCode

} catch {
 Write-Host ""
 Write-Host "Error occurred:" -ForegroundColor Red
 Write-Host $_.Exception.Message -ForegroundColor Red
 Write-Host ""
 if ($_.Exception.InnerException) {
  Write-Host "Inner exception:" -ForegroundColor Red
  Write-Host $_.Exception.InnerException.Message -ForegroundColor Red
  Write-Host ""
 }
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}

