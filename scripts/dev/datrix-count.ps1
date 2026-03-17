#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Count .dtrx and .dtrx.false files in subfolders of specified datrix directories

.DESCRIPTION
 Counts the number of files with .dtrx and .dtrx.false extensions under subfolders of:
 - datrix
 - datrix-cli
 - datrix-common
 - datrix-codegen-component
 - datrix-codegen-python
 - datrix-codegen-sql
 - datrix-codegen-typescript
 - datrix-common
 - datrix-language
 - datrix-codegen-aws
 - datrix-codegen-azure
 - datrix-codegen-docker
 - datrix-codegen-k8s

.EXAMPLE
 .\datrix-count.ps1
 Count .dtrx and .dtrx.false files in all specified directories.
#>

[CmdletBinding()]
param()

# Error handling
$ErrorActionPreference = "Stop"

# Import common module
$commonModulePath = Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) "common\DatrixPaths.psm1"
Import-Module $commonModulePath -Force

# Get workspace root and directories
$datrixWorkspaceRoot = Get-DatrixWorkspaceRoot -ScriptPath $MyInvocation.MyCommand.Path
$directories = Get-DatrixDirectories

Write-Host "Counting .dtrx and .dtrx.false files in subfolders..." -ForegroundColor Cyan
Write-Host ""

$totalDatrixCount = 0
$totalDatrixFalseCount = 0
$results = @()

foreach ($dir in $directories) {
 $dirPath = Join-Path $datrixWorkspaceRoot $dir
 
 if (-not (Test-Path $dirPath)) {
 Write-Warning "Directory not found: $dirPath"
 continue
 }
 
 # Get all .dtrx files in subfolders (recursive), excluding .dtrx.false files
 $datrixFiles = Get-ChildItem -Path $dirPath -Filter "*.dtrx" -Recurse -File -ErrorAction SilentlyContinue | 
 Where-Object { $_.Extension -eq ".dtrx" -and -not $_.Name.EndsWith(".dtrx.false") }
 $datrixCount = $datrixFiles.Count
 
 # Get all .dtrx.false files in subfolders (recursive)
 $datrixFalseFiles = Get-ChildItem -Path $dirPath -Filter "*.dtrx.false" -Recurse -File -ErrorAction SilentlyContinue
 $datrixFalseCount = $datrixFalseFiles.Count
 
 $totalDatrixCount += $datrixCount
 $totalDatrixFalseCount += $datrixFalseCount
 
 $result = [PSCustomObject]@{
 Directory = $dir
 ".dtrx" = $datrixCount
 ".dtrx.false" = $datrixFalseCount
 }
 $results += $result
}

# Display results
$results | Format-Table -AutoSize

Write-Host "Total .dtrx files: $totalDatrixCount" -ForegroundColor Green
Write-Host "Total .dtrx.false files: $totalDatrixFalseCount" -ForegroundColor Green

exit 0
