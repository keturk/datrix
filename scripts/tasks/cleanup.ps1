# Cleanup Task Files from .tasks Folders
# Lists all task files under .tasks folders of each datrix project
# If -Force parameter is provided, asks for confirmation before deletion
# If -Phase <number> is provided, only task files in phases before that number are considered (e.g. -Phase 60 deletes phases 1..59).
# Usage: .\scripts\tasks\cleanup.ps1 [-BaseDir <path>] [-Force] [-Phase <number>] [-Dbg]
# Example: .\scripts\tasks\cleanup.ps1 -Force -Phase 60

[CmdletBinding()]
param(
 [string]$BaseDir = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))),
 [switch]$Force,
 [int]$Phase = 0,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Import common cleanup utilities
$commonModulePath = Join-Path (Split-Path -Parent $PSScriptRoot) "common\CleanupUtils.psm1"
Import-Module $commonModulePath -Force

# Find all datrix projects
$projects = Get-ChildItem -Path $BaseDir -Directory | Where-Object { $_.Name -like "datrix*" }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Task Files Cleanup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allTaskFiles = @()

# Function to remove empty folders recursively (depth-first)
function Remove-EmptyFoldersRecursive {
 param(
 [string]$Path,
 [string]$BaseDir
 )
 
 if (-not (Test-Path $Path)) {
 return
 }
 
 # Normalize paths for comparison
 try {
 $normalizedPath = [System.IO.Path]::GetFullPath($Path).TrimEnd('\', '/')
 $normalizedBase = [System.IO.Path]::GetFullPath($BaseDir).TrimEnd('\', '/')
 
 # Don't remove folders at or above the base directory
 if ($normalizedPath -eq $normalizedBase) {
 return
 }
 $baseWithSeparator = $normalizedBase + [System.IO.Path]::DirectorySeparatorChar
 if (-not $normalizedPath.StartsWith($baseWithSeparator, [System.StringComparison]::OrdinalIgnoreCase)) {
 return
 }
 } catch {
 # Fallback: simple comparison
 if ($Path -eq $BaseDir) {
 return
 }
 }
 
 # First, recursively process subfolders (depth-first)
 # Get a snapshot of subfolders to process
 $subfolders = @()
 try {
 $subfolders = Get-ChildItem -Path $Path -Directory -ErrorAction Stop
 if ($null -ne $subfolders -and $subfolders.Count -gt 0) {
 # Convert to array if single item
 if ($subfolders -isnot [System.Array]) {
 $subfolders = @($subfolders)
 }
 foreach ($subfolder in $subfolders) {
 # Verify folder still exists before processing (it might have been removed by a previous operation)
 if (Test-Path $subfolder.FullName) {
 Remove-EmptyFoldersRecursive -Path $subfolder.FullName -BaseDir $BaseDir
 }
 }
 }
 } catch {
 # If we can't read the folder, skip it
 return
 }
 
 # Now check if this folder is empty (after subfolders have been processed)
 # Re-check in case folder was removed or changed
 if (-not (Test-Path $Path)) {
 return
 }
 
 try {
 $items = Get-ChildItem -Path $Path -ErrorAction Stop
 $isEmpty = $null -eq $items -or $items.Count -eq 0
 
 if ($isEmpty) {
 Remove-Item -Path $Path -Force -ErrorAction Stop
 Write-Host " Removed empty folder: $Path" -ForegroundColor DarkGreen
 }
 } catch {
 # If we can't check or remove, log a warning but continue
 Write-Host " Warning: Could not remove empty folder $Path : $_" -ForegroundColor DarkYellow
 }
}

# Function to collect task files from a folder
function Get-TaskFiles {
 param(
 [string]$TasksFolderPath,
 [string]$ProjectName
 )
 
 if (-not (Test-Path $TasksFolderPath)) {
 return
 }
 
 # Find all markdown files recursively
 $taskFiles = Get-ChildItem -Path $TasksFolderPath -Filter "*.md" -Recurse -File -ErrorAction SilentlyContinue
 
 # Handle case where Get-ChildItem returns a single object instead of an array
 if ($null -eq $taskFiles) {
 return
 }
 if ($taskFiles -isnot [System.Array]) {
 $taskFiles = @($taskFiles)
 }
 if ($taskFiles.Count -eq 0) {
 return
 }
 
 foreach ($taskFile in $taskFiles) {
 $phase = $null
 $tasksFolderNorm = [System.IO.Path]::GetFullPath($TasksFolderPath).TrimEnd('\', '/')
 $filePathNorm = [System.IO.Path]::GetFullPath($taskFile.FullName)
 if ($filePathNorm.StartsWith($tasksFolderNorm, [System.StringComparison]::OrdinalIgnoreCase)) {
 $relativePath = $filePathNorm.Substring($tasksFolderNorm.Length).TrimStart('\', '/')
 if ($relativePath -match 'phase-(\d+)') {
 $phase = [int]$matches[1]
 }
 }
 $script:allTaskFiles += @{
 Project = $ProjectName
 FullPath = $taskFile.FullName
 Name = $taskFile.Name
 Directory = $taskFile.DirectoryName
 Phase = $phase
 }
 }
}

# Process root .tasks folder
$rootTasksFolder = Join-Path $BaseDir ".tasks"
Get-TaskFiles -TasksFolderPath $rootTasksFolder -ProjectName "(root)"

# Process all datrix projects
foreach ($project in $projects) {
 $tasksFolder = Join-Path $project.FullName ".tasks"
 Get-TaskFiles -TasksFolderPath $tasksFolder -ProjectName $project.Name
}

# When -Phase is specified, keep only task files in phases before that number
if ($Phase -gt 0) {
 $allTaskFiles = @($allTaskFiles | Where-Object { $null -ne $_.Phase -and $_.Phase -lt $Phase })
}

# Collect all .tasks folders for cleanup (even if empty)
$allTasksFolders = @()
if (Test-Path $rootTasksFolder) {
 $allTasksFolders += @{
 Project = "(root)"
 Path = $rootTasksFolder
 }
}
foreach ($project in $projects) {
 $tasksFolder = Join-Path $project.FullName ".tasks"
 if (Test-Path $tasksFolder) {
 $allTasksFolders += @{
 Project = $project.Name
 Path = $tasksFolder
 }
 }
}

# Display all task files
if ($allTaskFiles.Count -eq 0) {
 Write-Host "No task files found in .tasks folders." -ForegroundColor Green
 Write-Host ""
 
 # Still show .tasks folders if they exist
 if ($allTasksFolders.Count -gt 0) {
 Write-Host "Found $($allTasksFolders.Count) .tasks folder(s) (may contain empty subfolders):" -ForegroundColor Cyan
 Write-Host ""
 foreach ($tasksFolderInfo in $allTasksFolders) {
 Write-Host "=== $($tasksFolderInfo.Project) ===" -ForegroundColor Cyan
 Write-Host " .tasks" -ForegroundColor White
 Write-Host " $($tasksFolderInfo.Path)" -ForegroundColor Gray
 
 $contents = Get-CleanupFolderContents -Path $tasksFolderInfo.Path -WarnOnFolderReadError
 if ($contents.Count -eq 0) {
 Write-Host " (empty)" -ForegroundColor DarkGray
 } else {
 foreach ($item in $contents) {
 $icon = if ($item.IsDirectory) { "[DIR]" } else { "[FILE]" }
 Write-Host "$($item.Indent)$icon $($item.Name)" -ForegroundColor DarkGray
 }
 }
 Write-Host ""
 }
 }
} else {
 Write-Host "Found $($allTaskFiles.Count) task file(s):" -ForegroundColor Cyan
 if ($Phase -gt 0) {
 Write-Host "Only task files in phases < $Phase will be deleted." -ForegroundColor Cyan
 }
 Write-Host ""

 # Display full list of all task files found
 Write-Host "Full list of task files:" -ForegroundColor Yellow
 Write-Host "----------------------------------------" -ForegroundColor Yellow
 $fileNumber = 1
 foreach ($file in $allTaskFiles) {
 Write-Host "$fileNumber. [$($file.Project)] $($file.FullPath)" -ForegroundColor White
 $fileNumber++
 }
 Write-Host "----------------------------------------" -ForegroundColor Yellow
 Write-Host ""

 # Group by project for display
 $groupedByProject = $allTaskFiles | Group-Object -Property Project

 foreach ($group in $groupedByProject) {
 Write-Host "=== $($group.Name) ===" -ForegroundColor Cyan
 
 # Get the .tasks folder path for this project
 $tasksFolderPath = if ($group.Name -eq "(root)") {
 Join-Path $BaseDir ".tasks"
 } else {
 $projectPath = Join-Path $BaseDir $group.Name
 Join-Path $projectPath ".tasks"
 }
 
 if (Test-Path $tasksFolderPath) {
 Write-Host " .tasks" -ForegroundColor White
 Write-Host " $tasksFolderPath" -ForegroundColor Gray
 
 # Display all files and subfolders
 $contents = Get-CleanupFolderContents -Path $tasksFolderPath -WarnOnFolderReadError
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
}

# If -Force is provided, ask for confirmation and delete
if ($Force) {
 $fileCount = $allTaskFiles.Count
 $folderCount = $allTasksFolders.Count
 
 Write-Host "========================================" -ForegroundColor Yellow
 if ($Phase -gt 0) {
 Write-Host "Only task files in phases < $Phase will be deleted." -ForegroundColor Yellow
 }
 if ($fileCount -gt 0) {
 Write-Host "WARNING: You are about to delete $fileCount task file(s)" -ForegroundColor Yellow
 }
 if ($folderCount -gt 0) {
 if ($fileCount -gt 0) {
 Write-Host "and clean up empty folders in $folderCount .tasks folder(s)" -ForegroundColor Yellow
 } else {
 Write-Host "WARNING: You are about to clean up empty folders in $folderCount .tasks folder(s)" -ForegroundColor Yellow
 }
 }
 Write-Host "========================================" -ForegroundColor Yellow
 Write-Host ""
 
 if (-not (Confirm-YesNo)) {
 Write-Host ""
 Write-Host "Deletion cancelled." -ForegroundColor Yellow
 exit 0
 }

 Write-Host ""
 $deletedCount = 0
 $errorCount = 0

 # First, delete all task files
 if ($fileCount -gt 0) {
 Write-Host "Deleting task files..." -ForegroundColor Yellow
 foreach ($file in $allTaskFiles) {
 try {
 Remove-Item -Path $file.FullPath -Force -ErrorAction Stop
 Write-Host " Deleted: $($file.FullPath)" -ForegroundColor Green
 $deletedCount++
 } catch {
 Write-Host " Error deleting $($file.FullPath): $_" -ForegroundColor Red
 $errorCount++
 }
 }
 }

 # Then, remove empty folders starting from the deepest level
 # Use the collected .tasks folders
 if ($allTasksFolders.Count -gt 0) {
 Write-Host ""
 Write-Host "Cleaning up empty folders..." -ForegroundColor Yellow
 foreach ($tasksFolderInfo in $allTasksFolders) {
 $tasksFolder = $tasksFolderInfo.Path
 if (Test-Path $tasksFolder) {
 # Remove empty subfolders recursively
 Remove-EmptyFoldersRecursive -Path $tasksFolder -BaseDir $BaseDir

 # Check if .tasks folder itself is now empty and remove it
 if (Test-Path $tasksFolder) {
 try {
 $items = Get-ChildItem -Path $tasksFolder -ErrorAction Stop
 if ($null -eq $items -or $items.Count -eq 0) {
 Remove-Item -Path $tasksFolder -Force -ErrorAction Stop
 Write-Host " Removed empty .tasks folder: $tasksFolder" -ForegroundColor DarkGreen
 }
 } catch {
 # Folder might have been removed or is not empty, continue
 }
 }
 }
 }
 }

 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 if ($fileCount -gt 0) {
 if ($errorCount -eq 0) {
 Write-Host "Successfully deleted $deletedCount file(s)" -ForegroundColor Green
 } else {
 Write-Host "Deleted $deletedCount file(s), $errorCount error(s)" -ForegroundColor Yellow
 }
 }
 if ($allTasksFolders.Count -gt 0) {
 Write-Host "Cleaned up empty folders in .tasks directories" -ForegroundColor Green
 }
 Write-Host "========================================" -ForegroundColor Cyan
} else {
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "To delete files and clean up empty folders, run with -Force parameter" -ForegroundColor Cyan
 Write-Host "Example: .\scripts\tasks\cleanup.ps1 -Force" -ForegroundColor Gray
 Write-Host "Example: .\scripts\tasks\cleanup.ps1 -Force -Phase 60  (delete only phases before 60)" -ForegroundColor Gray
 Write-Host "========================================" -ForegroundColor Cyan
}

Write-Host ""

exit 0
