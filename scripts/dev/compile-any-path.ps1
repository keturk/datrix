#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Compile (syntax + import check) for any Python path(s).

.DESCRIPTION
 Runs syntax and import checks on Python files under the given path(s). Unlike compile.ps1,
 this script works for any path: files, directories, or subfolders (e.g. a routes folder).
 For each path it finds the containing installable package and runs that package's full
 import check, so missing imports (e.g. db, Book) are reported.

 Activates the datrix virtual environment and runs compile_any_path.py.

.PARAMETER Path
 One or more file or directory paths to check (positional). Can be relative to current
 directory or absolute. Names are resolved against the workspace root if not rooted.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\compile-any-path.ps1 .\.generated\python\docker\01-tutorial\03-basic-api\library_book_service\src\library_book_service\routes
 Check the routes folder; import check runs for the containing library_book_service package.

.EXAMPLE
 .\compile-any-path.ps1 D:\datrix\datrix-common\src
 Check a src directory.
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$Path = @(),

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$pythonScript = Join-Path $libraryDir "dev\compile_any_path.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: compile_any_path.py not found at: $pythonScript"
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

if (-not $Path -or $Path.Count -eq 0) {
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host "  .\compile-any-path.ps1 <path> [path ...]" -ForegroundColor White
 Write-Host "  .\compile-any-path.ps1 .\.generated\...\library_book_service\src\...\routes" -ForegroundColor White
 Write-Host ""
 Write-Host "Use Get-Help .\compile-any-path.ps1 -Full for detailed help." -ForegroundColor Yellow
 exit 1
}

try {
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
  Write-Error "Failed to activate virtual environment"
  exit 1
 }

 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"
 $datrixWorkspaceRoot = Get-DatrixWorkspaceRoot

 $pathsToCheck = @()
 foreach ($p in $Path) {
  $fullPath = if ([System.IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $datrixWorkspaceRoot $p }
  if (Test-Path $fullPath) {
   $pathsToCheck += $fullPath
  } else {
   Write-Error "Path not found: $fullPath"
   exit 1
  }
 }

 $pythonArgs = @($pythonScript) + $pathsToCheck
 if ($Dbg) {
  $pythonArgs += "--debug"
 }

 Write-Host "Running compile (syntax and import check) for any path..." -ForegroundColor Cyan
 Write-Host ""

 & $pythonExe @pythonArgs
 exit $LASTEXITCODE

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
