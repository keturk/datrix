#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Count files with a specified extension in subfolders of specified datrix directories

.DESCRIPTION
 Counts the number of files with a specified extension under subfolders of:
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

.PARAMETER Extension
 The file extension to count (without leading dot). Defaults to "j2".

.EXAMPLE
 .\file-count.ps1
 Count .j2 files in all specified directories (default).

.EXAMPLE
 .\file-count.ps1 py
 Count .py files in all specified directories.

.EXAMPLE
 .\file-count.ps1 datrix
 Count .dtrx files in all specified directories.

.EXAMPLE
 .\file-count.ps1 exe
 Count .exe files in all specified directories.
#>

[CmdletBinding()]
param(
 [Parameter(Mandatory=$false, Position=0)]
 [string]$Extension = "j2"
)

# Error handling
$ErrorActionPreference = "Stop"

# Normalize extension (ensure it starts with a dot)
if (-not $Extension.StartsWith(".")) {
 $Extension = ".$Extension"
}

# Import common module
$commonModulePath = Join-Path (Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Path)) "common\DatrixPaths.psm1"
Import-Module $commonModulePath -Force

# Get workspace root and directories
$datrixWorkspaceRoot = Get-DatrixWorkspaceRoot -ScriptPath $MyInvocation.MyCommand.Path
$directories = Get-DatrixDirectories

Write-Host "Counting $Extension files in subfolders..." -ForegroundColor Cyan
Write-Host ""

$totalCount = 0
$results = @()

foreach ($dir in $directories) {
 $dirPath = Join-Path $datrixWorkspaceRoot $dir
 
 if (-not (Test-Path $dirPath)) {
 Write-Warning "Directory not found: $dirPath"
 continue
 }
 
 # Get all files with the specified extension in subfolders (recursive)
 $filter = "*$Extension"
 $files = Get-ChildItem -Path $dirPath -Filter $filter -Recurse -File -ErrorAction SilentlyContinue
 $fileCount = $files.Count
 
 $totalCount += $fileCount
 
 $result = [PSCustomObject]@{
 Directory = $dir
 $Extension = $fileCount
 }
 $results += $result
}

# Display results
$results | Format-Table -AutoSize

Write-Host "Total $Extension files: $totalCount" -ForegroundColor Green

exit 0
