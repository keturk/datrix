#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Compile Python (syntax + import check) in Datrix projects, or under any path

.DESCRIPTION
 Two parameter sets:

 Projects (-All or positional project directories): compiles every Python file of the named
 Datrix projects (lib\compile.py) to find syntax and import issues.

 Path (-Path): checks Python files under any file or directory (a generated service's routes
 folder, say). For each path it finds the containing installable package and runs that
 package's full import check, so a missing import is reported (lib\compile_any_path.py).

 Relative names and paths resolve against the workspace root.

.PARAMETER All
 Compile Python in all datrix repositories (same list as Get-DatrixDirectoryPaths).

.PARAMETER ProjectDir
 One or more project directories to check (positional). Can be names (e.g. datrix-common)
 or full paths.

.PARAMETER Path
 One or more files or directories to check, anywhere (e.g. a generated service's folder).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\compile.ps1 -All
 Check all Python files in all datrix repositories.

.EXAMPLE
 .\compile.ps1 datrix-common datrix-language -Dbg
 Check two projects with debug output.

.EXAMPLE
 .\compile.ps1 -Path D:\datrix\.generated\python\docker\02-features\01-core-data-modeling\rest-api\library_book_service\src\library_book_service\routes
 Check the routes folder; the import check runs for the containing library_book_service package.
#>

[CmdletBinding(DefaultParameterSetName = "Projects")]
param(
 [Parameter(ParameterSetName = "Projects")]
 [switch]$All,

 [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Projects")]
 [string[]]$ProjectDir = @(),

 [Parameter(Mandatory = $true, ParameterSetName = "Path")]
 [string[]]$Path,

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

function Resolve-CompileTarget {
 # A rooted path as-is; a name or relative path against the workspace root. Missing is an error.
 param([string]$Target)
 $fullPath = if ([System.IO.Path]::IsPathRooted($Target)) { $Target } else { Join-Path (Get-DatrixWorkspaceRoot) $Target }
 if (-not (Test-Path $fullPath)) {
  Write-Host "ERROR: Path not found: $fullPath. Pass a project name (datrix-common), or a file or directory path." -ForegroundColor Red
  exit 2
 }
 return $fullPath
}

if ($PSCmdlet.ParameterSetName -eq "Path") {
 $pythonScript = Join-Path $PSScriptRoot "lib\compile_any_path.py"
 $pathsToCheck = @($Path | ForEach-Object { $_ -split "," } | Where-Object { $_ } | ForEach-Object { Resolve-CompileTarget $_ })
 Write-Host "Running compile (syntax and import check) for any path..." -ForegroundColor Cyan
} else {
 if (-not $All -and $ProjectDir.Count -eq 0) {
  Write-Host "Usage:" -ForegroundColor Yellow
  Write-Host "  .\compile.ps1 -All" -ForegroundColor White
  Write-Host "  .\compile.ps1 datrix-common [datrix-language ...]" -ForegroundColor White
  Write-Host "  .\compile.ps1 -Path <file or directory> [...]" -ForegroundColor White
  Write-Host ""
  Write-Host "Use Get-Help .\compile.ps1 -Full for detailed help." -ForegroundColor Yellow
  exit 2
 }
 $pythonScript = Join-Path $PSScriptRoot "lib\compile.py"
 $pathsToCheck = if ($All) {
  @(Get-DatrixDirectoryPaths | Where-Object { Test-Path $_ })
 } else {
  @($ProjectDir | ForEach-Object { Resolve-CompileTarget $_ })
 }
 Write-Host "Running compile (syntax and import check)..." -ForegroundColor Cyan
}
Write-Host ""

$pythonArgs = @($pathsToCheck)
if ($Dbg) {
 $pythonArgs += "--debug"
}
exit (Invoke-DatrixPythonScript -Script $pythonScript -Arguments $pythonArgs -ShowCommand:$Dbg)
