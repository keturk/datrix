#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if Python bytecode files are present under package src directories.

.DESCRIPTION
 Scans Datrix package src/ trees for .pyc/.pyo files and __pycache__
 directories. The script is intentionally standalone and does not activate the
 shared Python virtual environment, so it can run before other checks.

.PARAMETER BaseDir
 Monorepo root directory. Defaults to the parent workspace containing this script.

.PARAMETER ProjectDir
 Optional project names or paths to check. Defaults to all datrix package
 directories under BaseDir that have a src directory.
#>

[CmdletBinding()]
param(
 [Parameter()]
 [string]$BaseDir = "",

 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$ProjectDir = @()
)

$ErrorActionPreference = "Stop"

if ([string]::IsNullOrWhiteSpace($BaseDir)) {
 $scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
 $BaseDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
}

$baseFull = [System.IO.Path]::GetFullPath($BaseDir).TrimEnd('\', '/')
if (-not (Test-Path -LiteralPath $baseFull)) {
 Write-Error "BaseDir not found: $baseFull"
 exit 2
}

$srcRoots = @()
if ($ProjectDir.Count -gt 0) {
 foreach ($p in $ProjectDir) {
  $projectPath = if ([System.IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $baseFull $p }
  $srcPath = Join-Path $projectPath "src"
  if (-not (Test-Path -LiteralPath $srcPath)) {
   Write-Error "src directory not found: $srcPath"
   exit 2
  }
  $srcRoots += [System.IO.Path]::GetFullPath($srcPath).TrimEnd('\', '/')
 }
} else {
 $srcRoots = @(
  Get-ChildItem -LiteralPath $baseFull -Directory -ErrorAction Stop |
   Where-Object { $_.Name -like "datrix*" -and (Test-Path -LiteralPath (Join-Path $_.FullName "src")) } |
   ForEach-Object { [System.IO.Path]::GetFullPath((Join-Path $_.FullName "src")).TrimEnd('\', '/') }
 )
}

foreach ($srcRoot in $srcRoots) {
 if (-not $srcRoot.StartsWith($baseFull, [System.StringComparison]::OrdinalIgnoreCase)) {
  Write-Error "Refusing to scan path outside BaseDir: $srcRoot"
  exit 2
 }
}

$bytecodeFiles = @(
 Get-ChildItem -LiteralPath $srcRoots -Recurse -File -Force -ErrorAction SilentlyContinue |
  Where-Object { $_.Extension -in ".pyc", ".pyo" }
)
$pycacheDirs = @(
 Get-ChildItem -LiteralPath $srcRoots -Recurse -Directory -Filter "__pycache__" -Force -ErrorAction SilentlyContinue
)

if ($bytecodeFiles.Count -eq 0 -and $pycacheDirs.Count -eq 0) {
 Write-Host "No Python bytecode found under package src directories." -ForegroundColor Green
 exit 0
}

Write-Host "Python bytecode artifacts found under package src directories:" -ForegroundColor Red
foreach ($path in ($bytecodeFiles.FullName + $pycacheDirs.FullName | Sort-Object)) {
 Write-Host "  $path" -ForegroundColor Red
}
Write-Host ""
Write-Host "Remove these artifacts or run Python with PYTHONPYCACHEPREFIX outside src." -ForegroundColor Yellow
exit 1
