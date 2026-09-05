# Cleanup Ruff Check Output
# Lists all log files under the workspace-level .test-output\ruff\<project>\ folders
# written by metrics\ruff.ps1. Those logs live outside every package repo on purpose:
# each datrix-* package is its own git repository, so run output created inside one
# is committed and pushed unless a human notices.
# If -Force is provided, deletes those files and removes each per-project folder if empty.
# Usage: .\scripts\metrics\cleanup-ruff.ps1 [-BaseDir <path>] [-Force] [-KeepLatest] [-Dbg]

[CmdletBinding()]
param(
 [string]$BaseDir,
 [switch]$Force,
 [switch]$KeepLatest,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# $PSScriptRoot is empty while param() defaults are bound under `powershell -File`,
# so the workspace root is resolved here from the script's own path instead --
# the same shape ruff.ps1 uses. As a param default it made every invocation abort
# on "Cannot bind argument to parameter 'Path' because it is an empty string".
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
if (-not $BaseDir) {
 $BaseDir = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $scriptDir))
}

# Import common cleanup utilities
$commonModulePath = Join-Path (Split-Path -Parent $scriptDir) "common\CleanupUtils.psm1"
Import-Module $commonModulePath -Force

$RUFF_LOG_ROOT = Join-Path $BaseDir ".test-output\ruff"

# One folder per project under the workspace-level ruff log root
$projects = if (Test-Path $RUFF_LOG_ROOT) {
 Get-ChildItem -Path $RUFF_LOG_ROOT -Directory
} else {
 @()
}

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Ruff Check Output Cleanup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allFiles = [System.Collections.ArrayList]@()
$totalSize = 0

# Function to collect a project's ruff log files
function Get-RuffCheckFiles {
 param(
 [string]$RuffLogPath,
 [string]$ProjectName
 )

 if (-not (Test-Path $RuffLogPath)) {
 return
 }

 $files = Get-ChildItem -Path $RuffLogPath -File -ErrorAction SilentlyContinue
 if ($null -eq $files -or $files.Count -eq 0) {
 return
 }
 if ($files -isnot [System.Array]) {
 $files = @($files)
 }

 # Sort by name descending (ruff-YYYYMMdd-HHmmss.log => newest first)
 $sortedFiles = $files | Sort-Object Name -Descending
 $isFirst = $true

 foreach ($file in $sortedFiles) {
 $script:totalSize += $file.Length
 $fileInfo = [PSCustomObject]@{
 Project = $ProjectName
 FullPath = $file.FullName
 Name = $file.Name
 Size = $file.Length
 IsLatest = $isFirst
 ParentDir = $RuffLogPath
 }
 $null = $script:allFiles.Add($fileInfo)
 $isFirst = $false
 }
}

# Process every per-project log folder
foreach ($project in $projects) {
 Get-RuffCheckFiles -RuffLogPath $project.FullName -ProjectName $project.Name
}

# Display all files
if ($allFiles.Count -eq 0) {
 Write-Host "No Ruff check log files found." -ForegroundColor Green
 Write-Host ""
 exit 0
}

Write-Host "Found $($allFiles.Count) file(s) (Total: $(Format-CleanupSize -Size $totalSize)):" -ForegroundColor Cyan
Write-Host ""

$groupedByProject = $allFiles | Group-Object -Property Project

foreach ($group in $groupedByProject) {
 Write-Host "=== $($group.Name) ===" -ForegroundColor Cyan
 foreach ($file in $group.Group) {
 $latestTag = if ($file.IsLatest) { " [LATEST]" } else { "" }
 $color = if ($file.IsLatest) { "Green" } else { "White" }
 Write-Host " $($file.Name) ($(Format-CleanupSize -Size $file.Size))$latestTag" -ForegroundColor $color
 Write-Host " $($file.FullPath)" -ForegroundColor Gray
 }
 Write-Host ""
}

# Determine what to delete
$filesToDelete = @($allFiles)
if ($KeepLatest) {
 $filesToDelete = @($allFiles | Where-Object { -not $_.IsLatest })
}

$deleteSize = 0
foreach ($f in $filesToDelete) {
 $deleteSize += $f.Size
}

# If -Force is provided, ask for confirmation and delete
if ($Force) {
 if ($filesToDelete.Count -eq 0) {
 Write-Host "No files to delete (keeping latest log per project)." -ForegroundColor Green
 Write-Host ""
 exit 0
 }

 Write-Host "========================================" -ForegroundColor Yellow
 if ($KeepLatest) {
 Write-Host "WARNING: You are about to delete $($filesToDelete.Count) old log file(s)" -ForegroundColor Yellow
 Write-Host " (keeping latest log for each project)" -ForegroundColor Yellow
 } else {
 Write-Host "WARNING: You are about to delete ALL $($filesToDelete.Count) log file(s)" -ForegroundColor Yellow
 }
 Write-Host " Total size: $(Format-CleanupSize -Size $deleteSize)" -ForegroundColor Yellow
 Write-Host "========================================" -ForegroundColor Yellow
 Write-Host ""

 if (-not (Confirm-YesNo)) {
 Write-Host ""
 Write-Host "Deletion cancelled." -ForegroundColor Yellow
 exit 0
 }

 Write-Host ""
 Write-Host "Deleting log files..." -ForegroundColor Yellow

 $deletedCount = 0
 $errorCount = 0
 $deletedSize = 0
 $parentDirsToCheck = @{}

 foreach ($file in $filesToDelete) {
 try {
 Remove-Item -Path $file.FullPath -Force -ErrorAction Stop
 Write-Host " Deleted: $($file.FullPath)" -ForegroundColor Green
 $deletedCount++
 $deletedSize += $file.Size
 $parentDirsToCheck[$file.ParentDir] = $true
 } catch {
 Write-Host " Error deleting $($file.FullPath): $_" -ForegroundColor Red
 $errorCount++
 }
 }

 # Remove the per-project log folder if empty
 foreach ($parentDir in $parentDirsToCheck.Keys) {
 if (-not (Test-Path $parentDir)) {
 continue
 }
 $remaining = Get-ChildItem -Path $parentDir -ErrorAction SilentlyContinue
 if ($null -eq $remaining -or $remaining.Count -eq 0) {
 try {
 Remove-Item -Path $parentDir -Force -ErrorAction Stop
 Write-Host " Removed empty folder: $parentDir" -ForegroundColor DarkGreen
 } catch {
 Write-Host " Error removing folder $parentDir : $_" -ForegroundColor Red
 }
 }
 }

 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 if ($errorCount -eq 0) {
 Write-Host "Successfully deleted $deletedCount file(s) ($(Format-CleanupSize -Size $deletedSize))" -ForegroundColor Green
 } else {
 Write-Host "Deleted $deletedCount file(s), $errorCount error(s)" -ForegroundColor Yellow
 }
 Write-Host "========================================" -ForegroundColor Cyan
} else {
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "To delete these files, run with -Force parameter" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Options:" -ForegroundColor Gray
 Write-Host " .\cleanup-ruff.ps1 -Force # Delete all log files and empty per-project folders" -ForegroundColor Gray
 Write-Host " .\cleanup-ruff.ps1 -Force -KeepLatest # Keep latest log per project" -ForegroundColor Gray
 Write-Host "========================================" -ForegroundColor Cyan
}

Write-Host ""

exit 0

