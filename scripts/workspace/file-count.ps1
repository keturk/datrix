#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Count files with one or more extensions in subfolders of every datrix directory

.DESCRIPTION
 Counts the files whose name ends with each given extension under every datrix repository
discovered by Get-DatrixDirectories (the datrix showcase repo plus every datrix-* package directory in
the workspace), one column per extension. The set is discovered from disk, never hardcoded, so a new
package is covered with no edit here. A file is counted under an extension only when its name ends
with it, so "x.dtrx.false" counts as dtrx.false, never as dtrx.

.PARAMETER Extension
 The file extensions to count (without the leading dot). Defaults to "j2".

.EXAMPLE
 .\file-count.ps1
 Count .j2 files in all directories (default).

.EXAMPLE
 .\file-count.ps1 py
 Count .py files in all directories.

.EXAMPLE
 .\file-count.ps1 -Extension dtrx,dtrx.false
 Count .dtrx and .dtrx.false files, one column each.
#>

[CmdletBinding()]
param(
 [Parameter(Mandatory=$false, Position=0)]
 [string[]]$Extension = @("j2")
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force

# "powershell -File" passes "dtrx,dtrx.false" as one string, so a comma list is split here;
# each extension is normalized to start with a dot.
$extensions = @($Extension | ForEach-Object { $_ -split "," } | Where-Object { $_ } |
 ForEach-Object { if ($_.StartsWith(".")) { $_ } else { ".$_" } })

$datrixWorkspaceRoot = Get-DatrixWorkspaceRoot
$directories = Get-DatrixDirectories

Write-Host "Counting $($extensions -join ', ') files in subfolders..." -ForegroundColor Cyan
Write-Host ""

$totals = [ordered]@{}
foreach ($ext in $extensions) { $totals[$ext] = 0 }
$results = @()

foreach ($dir in $directories) {
 $dirPath = Join-Path $datrixWorkspaceRoot $dir
 if (-not (Test-Path $dirPath)) {
  Write-Warning "Directory not found: $dirPath"
  continue
 }
 $names = @(Get-ChildItem -Path $dirPath -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object { $_.Name })
 $row = [ordered]@{ Directory = $dir }
 foreach ($ext in $extensions) {
  $count = @($names | Where-Object { $_.EndsWith($ext, [System.StringComparison]::OrdinalIgnoreCase) }).Count
  $row[$ext] = $count
  $totals[$ext] += $count
 }
 $results += [PSCustomObject]$row
}

$results | Format-Table -AutoSize

foreach ($ext in $extensions) {
 Write-Host "Total $ext files: $($totals[$ext])" -ForegroundColor Green
}

exit 0
