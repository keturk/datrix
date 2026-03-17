# Cleanup Empty Folders
# Recursively finds and lists all empty folders starting from the specified path
# If -Force parameter is provided, asks for confirmation before deletion
# Usage: .\scripts\dev\empty-folders.ps1 [-Path <path>] [-Force] [-Dbg]

[CmdletBinding()]
param(
 [string]$Path = (Get-Location).Path,
 [switch]$Force,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Import common cleanup utilities
$commonModulePath = Join-Path (Split-Path -Parent $PSScriptRoot) "common\CleanupUtils.psm1"
Import-Module $commonModulePath -Force

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Empty Folders Cleanup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Validate path
if (-not (Test-Path $Path)) {
 Write-Host "Error: Path '$Path' does not exist." -ForegroundColor Red
 exit 1
}

if (-not (Test-Path $Path -PathType Container)) {
 Write-Host "Error: Path '$Path' is not a directory." -ForegroundColor Red
 exit 1
}

$Path = (Resolve-Path $Path).Path
Write-Host "Searching for empty folders in: $Path" -ForegroundColor Cyan
Write-Host ""

# Function to check if a folder is empty
function Test-EmptyFolder {
 param([string]$FolderPath)
 
 try {
 $items = Get-ChildItem -Path $FolderPath -ErrorAction SilentlyContinue
 return ($null -eq $items -or $items.Count -eq 0)
 } catch {
 return $false
 }
}

# Function to get folder depth (number of path separators)
function Get-FolderDepth {
 param([string]$FolderPath)
 
 $normalizedPath = [System.IO.Path]::GetFullPath($FolderPath).TrimEnd('\', '/')
 $pathParts = $normalizedPath -split [regex]::Escape([System.IO.Path]::DirectorySeparatorChar)
 return $pathParts.Count
}

# Find all empty folders recursively
Write-Host "Scanning for empty folders..." -ForegroundColor Yellow
$allEmptyFolders = [System.Collections.ArrayList]@()

# Get all directories recursively
$allDirectories = Get-ChildItem -Path $Path -Directory -Recurse -ErrorAction SilentlyContinue

# Also include the root path if it's empty
if (Test-EmptyFolder -FolderPath $Path) {
 $null = $allEmptyFolders.Add([PSCustomObject]@{
 FullPath = $Path
 Name = Split-Path -Leaf $Path
 Depth = Get-FolderDepth -FolderPath $Path
 })
}

# Check each directory
foreach ($dir in $allDirectories) {
 if (Test-EmptyFolder -FolderPath $dir.FullName) {
 $null = $allEmptyFolders.Add([PSCustomObject]@{
 FullPath = $dir.FullName
 Name = $dir.Name
 Depth = Get-FolderDepth -FolderPath $dir.FullName
 })
 }
}

# Display results
if ($allEmptyFolders.Count -eq 0) {
 Write-Host "No empty folders found." -ForegroundColor Green
 Write-Host ""
 exit 0
}

Write-Host "Found $($allEmptyFolders.Count) empty folder(s):" -ForegroundColor Cyan
Write-Host ""

# Sort by depth (deepest first) for display and deletion
$sortedFolders = $allEmptyFolders | Sort-Object -Property Depth -Descending

Write-Host "Empty folders (deepest first):" -ForegroundColor Yellow
Write-Host "----------------------------------------" -ForegroundColor Yellow
$folderNumber = 1
foreach ($folder in $sortedFolders) {
 Write-Host "$folderNumber. $($folder.FullPath)" -ForegroundColor White
 $folderNumber++
}
Write-Host "----------------------------------------" -ForegroundColor Yellow
Write-Host ""

# If -Force is provided, ask for confirmation and delete
if ($Force) {
 Write-Host "========================================" -ForegroundColor Yellow
 Write-Host "WARNING: You are about to delete $($allEmptyFolders.Count) empty folder(s)" -ForegroundColor Yellow
 Write-Host "========================================" -ForegroundColor Yellow
 Write-Host ""
 
 if (-not (Confirm-YesNo)) {
 Write-Host ""
 Write-Host "Deletion cancelled." -ForegroundColor Yellow
 exit 0
 }

 Write-Host ""
 Write-Host "Deleting empty folders..." -ForegroundColor Yellow

 $deletedCount = 0
 $errorCount = 0

 # Delete from deepest to shallowest to avoid issues
 foreach ($folder in $sortedFolders) {
 try {
 # Double-check folder is still empty before deleting
 if (Test-EmptyFolder -FolderPath $folder.FullPath) {
 Remove-Item -Path $folder.FullPath -Force -ErrorAction Stop
 Write-Host " Deleted: $($folder.FullPath)" -ForegroundColor Green
 $deletedCount++
 } else {
 Write-Host " Skipped (no longer empty): $($folder.FullPath)" -ForegroundColor DarkYellow
 }
 } catch {
 Write-Host " Error deleting $($folder.FullPath): $_" -ForegroundColor Red
 $errorCount++
 }
 }

 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 if ($errorCount -eq 0) {
 Write-Host "Successfully deleted $deletedCount empty folder(s)" -ForegroundColor Green
 } else {
 Write-Host "Deleted $deletedCount folder(s), $errorCount error(s)" -ForegroundColor Yellow
 }
 Write-Host "========================================" -ForegroundColor Cyan
} else {
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "To delete these folders, run with -Force parameter" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Gray
 Write-Host " .\scripts\dev\empty-folders.ps1 -Force # Delete empty folders in current directory" -ForegroundColor Gray
 Write-Host " .\scripts\dev\empty-folders.ps1 -Path <path> -Force # Delete empty folders in specified path" -ForegroundColor Gray
 Write-Host "========================================" -ForegroundColor Cyan
}

Write-Host ""

exit 0
