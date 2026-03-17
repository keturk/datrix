# Cleanup Test Results Folders
# Lists all .test_results folders in datrix projects and under .generated (recursively)
# If -Force parameter is provided, asks for confirmation before deletion
# Usage: .\scripts\test\cleanup.ps1 [-BaseDir <path>] [-Force] [-Dbg]

[CmdletBinding()]
param(
 [string]$BaseDir = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))),
 [switch]$Force,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Import common cleanup utilities
$commonModulePath = Join-Path (Split-Path -Parent $PSScriptRoot) "common\CleanupUtils.psm1"
Import-Module $commonModulePath -Force

# Find all datrix projects
$projects = Get-ChildItem -Path $BaseDir -Directory | Where-Object { $_.Name -like "datrix*" }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Test Results Cleanup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allTestResultsFolders = [System.Collections.ArrayList]@()
$totalSize = 0

# Function to get folder size
function Get-FolderSize {
 param([string]$Path)

 $size = 0
 Get-ChildItem -Path $Path -Recurse -File -ErrorAction SilentlyContinue | ForEach-Object {
 $size += $_.Length
 }
 return $size
}

# Function to format size
function Format-Size {
 param([long]$Size)

 if ($Size -ge 1GB) {
 return "{0:N2} GB" -f ($Size / 1GB)
 } elseif ($Size -ge 1MB) {
 return "{0:N2} MB" -f ($Size / 1MB)
 } elseif ($Size -ge 1KB) {
 return "{0:N2} KB" -f ($Size / 1KB)
 } else {
 return "$Size bytes"
 }
}

# Function to get folder contents recursively
function Get-FolderContents {
 param(
 [string]$Path,
 [string]$Indent = " "
 )

 $contents = [System.Collections.ArrayList]@()
 
 if (-not (Test-Path $Path)) {
 return $contents
 }

 $items = Get-ChildItem -Path $Path -ErrorAction SilentlyContinue | Sort-Object Name
 
 foreach ($item in $items) {
 $itemInfo = [PSCustomObject]@{
 Name = $item.Name
 FullPath = $item.FullName
 IsDirectory = $item.PSIsContainer
 Indent = $Indent
 }
 $null = $contents.Add($itemInfo)
 
 # Recursively get subfolder contents (loop Add to avoid PowerShell passing ArrayList as single object to AddRange)
 if ($item.PSIsContainer) {
 $subContents = Get-FolderContents -Path $item.FullName -Indent "$Indent "
 if ($null -ne $subContents -and $subContents.Count -gt 0) {
 foreach ($subItem in $subContents) {
 $null = $contents.Add($subItem)
 }
 }
 }
 }
 
 return $contents
}

# Function to collect test results folders
function Get-TestResultsFolders {
 param(
 [string]$TestResultsPath,
 [string]$ParentName
 )

 if (-not (Test-Path $TestResultsPath)) {
 return
 }

 $size = Get-FolderSize -Path $TestResultsPath
 $script:totalSize += $size

 $testResultsInfo = [PSCustomObject]@{
 Parent = $ParentName
 FullPath = $TestResultsPath
 Size = $size
 }
 $null = $script:allTestResultsFolders.Add($testResultsInfo)
}

# Process all datrix projects
foreach ($project in $projects) {
 $testResultsFolder = Join-Path $project.FullName ".test_results"
 Get-TestResultsFolders -TestResultsPath $testResultsFolder -ParentName $project.Name
}

# Process .generated folder: all .test_results at root and under subdirs
$generatedFolder = Join-Path $BaseDir ".generated"
if (Test-Path $generatedFolder) {
 $generatedFolderNorm = $generatedFolder.TrimEnd('\', '/')
 Get-ChildItem -Path $generatedFolder -Filter ".test_results" -Recurse -Directory -ErrorAction SilentlyContinue | ForEach-Object {
  $parentFull = $_.Parent.FullName.TrimEnd('\', '/')
  $parentRelative = if ($parentFull -eq $generatedFolderNorm) { "." } else { $parentFull.Substring($generatedFolderNorm.Length).TrimStart('\', '/') }
  $parentName = if ($parentRelative -eq ".") { ".generated" } else { ".generated\$parentRelative" }
  Get-TestResultsFolders -TestResultsPath $_.FullName -ParentName $parentName
 }
}

# Display all test results folders
if ($allTestResultsFolders.Count -eq 0) {
 Write-Host "No .test_results folders found." -ForegroundColor Green
 Write-Host ""
 exit 0
}

Write-Host "Found $($allTestResultsFolders.Count) .test_results folder(s) (Total: $(Format-Size $totalSize)):" -ForegroundColor Cyan
Write-Host ""

# Group by parent for display
$groupedByParent = $allTestResultsFolders | Group-Object -Property Parent

foreach ($group in $groupedByParent) {
 Write-Host "=== $($group.Name) ===" -ForegroundColor Cyan
 foreach ($folder in $group.Group) {
 Write-Host " .test_results ($(Format-Size $folder.Size))" -ForegroundColor White
 Write-Host " $($folder.FullPath)" -ForegroundColor Gray
 
 # Display all files and subfolders
 $contents = Get-FolderContents -Path $folder.FullPath
 if ($contents.Count -eq 0) {
 Write-Host " (empty)" -ForegroundColor DarkGray
 } else {
 foreach ($item in $contents) {
 $icon = if ($item.IsDirectory) { "[DIR]" } else { "[FILE]" }
 Write-Host "$($item.Indent)$icon $($item.Name)" -ForegroundColor DarkGray
 }
 }
 }
 Write-Host ""
}

# If -Force is provided, ask for confirmation and delete
if ($Force) {
 Write-Host "========================================" -ForegroundColor Yellow
 Write-Host "WARNING: You are about to delete ALL $($allTestResultsFolders.Count) .test_results folder(s)" -ForegroundColor Yellow
 Write-Host " Total size: $(Format-Size $totalSize)" -ForegroundColor Yellow
 Write-Host "========================================" -ForegroundColor Yellow
 Write-Host ""

 if (-not (Confirm-YesNo)) {
 Write-Host ""
 Write-Host "Deletion cancelled." -ForegroundColor Yellow
 exit 0
 }

 Write-Host ""
 Write-Host "Deleting .test_results folders..." -ForegroundColor Yellow

 $deletedCount = 0
 $errorCount = 0
 $deletedSize = 0

 foreach ($folder in $allTestResultsFolders) {
 try {
 Remove-Item -Path $folder.FullPath -Recurse -Force -ErrorAction Stop
 Write-Host " Deleted: $($folder.FullPath)" -ForegroundColor Green
 $deletedCount++
 $deletedSize += $folder.Size

 # Remove empty parent folders
 Remove-EmptyParentFolders -ItemPath $folder.FullPath -BaseDir $BaseDir
 } catch {
 Write-Host " Error deleting $($folder.FullPath): $_" -ForegroundColor Red
 $errorCount++
 }
 }

 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 if ($errorCount -eq 0) {
 Write-Host "Successfully deleted $deletedCount folder(s) ($(Format-Size $deletedSize))" -ForegroundColor Green
 } else {
 Write-Host "Deleted $deletedCount folder(s), $errorCount error(s)" -ForegroundColor Yellow
 }
 Write-Host "========================================" -ForegroundColor Cyan
} else {
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "To delete these folders, run with -Force parameter" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Gray
 Write-Host " .\scripts\test\cleanup.ps1 -Force # Delete all .test_results folders" -ForegroundColor Gray
 Write-Host "========================================" -ForegroundColor Cyan
}

Write-Host ""

exit 0
