# List Incomplete Tasks and Bugs from .tasks and .bugs Folders
# Scans all datrix projects for incomplete tasks (those without "COMPLETED: " prefix)
# and incomplete bugs (those without "FIXED: " prefix)
# Usage: .\scripts\tasks\todo.ps1 [-BaseDir <path>] [-Filter <string>] [-Dbg]
# -Filter: when provided, only list tasks/bugs whose file name OR title contains the string (case-insensitive).

[CmdletBinding()]
param(
 [string]$BaseDir = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))),
 [string]$Filter = "",
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

. (Join-Path $PSScriptRoot "common.ps1")

# Find all datrix projects
$projects = Get-ChildItem -Path $BaseDir -Directory | Where-Object { $_.Name -like "datrix*" }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Incomplete Tasks and Bugs Summary" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allIncompleteTasks = @()
$allIncompleteBugs = @()
$totalTaskCount = 0
$totalBugCount = 0

# Function to process tasks folder
function Process-TasksFolder {
 param(
 [string]$TasksFolderPath,
 [string]$ProjectName,
 [string]$BasePath,
 [string]$Filter = ""
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
 
 $projectTasks = @()
 
 foreach ($taskFile in $taskFiles) {
 try {
 $content = Get-Content -Path $taskFile.FullName -Raw -ErrorAction Stop
 
 if ([string]::IsNullOrWhiteSpace($content)) {
 continue
 }
 
 $firstHeading = Get-FirstMarkdownHeading -Content $content
 if ([string]::IsNullOrWhiteSpace($firstHeading)) {
 continue
 }
 
 # Only consider headings that start with "Task " as actual tasks
 if ($firstHeading -notmatch '^Task\s+') {
 continue
 }
 
 # Check if task is completed (starts with "COMPLETED: Task ")
 if ($firstHeading -match '^COMPLETED:\s+Task\s') {
 continue
 }
 
 if (-not (Test-ItemMatchesFilter -FileName $taskFile.Name -Title $firstHeading -Filter $Filter)) {
 continue
 }
 
 # This is an incomplete task
 $relativePath = $taskFile.FullName.Substring($BasePath.Length + 1)
 $projectTasks += @{
 File = $relativePath
 Title = $firstHeading
 FullPath = $taskFile.FullName
 }
 $script:totalTaskCount++
 } catch {
 # Skip files that can't be read
 Write-Host " Warning: Could not read $($taskFile.Name): $_" -ForegroundColor Yellow
 continue
 }
 }
 
 if ($projectTasks.Count -gt 0) {
 $script:allIncompleteTasks += @{
 Project = $ProjectName
 Tasks = $projectTasks
 }
 }
}

# Function to process bugs folder
function Process-BugsFolder {
 param(
 [string]$BugsFolderPath,
 [string]$ProjectName,
 [string]$BasePath,
 [string]$Filter = ""
 )
 
 if (-not (Test-Path $BugsFolderPath)) {
 return
 }
 
 # Find all markdown files recursively
 $bugFiles = Get-ChildItem -Path $BugsFolderPath -Filter "*.md" -Recurse -File -ErrorAction SilentlyContinue
 
 # Handle case where Get-ChildItem returns a single object instead of an array
 if ($null -eq $bugFiles) {
 return
 }
 if ($bugFiles -isnot [System.Array]) {
 $bugFiles = @($bugFiles)
 }
 if ($bugFiles.Count -eq 0) {
 return
 }
 
 $projectBugs = @()
 
 foreach ($bugFile in $bugFiles) {
 try {
 $content = Get-Content -Path $bugFile.FullName -Raw -ErrorAction Stop
 
 if ([string]::IsNullOrWhiteSpace($content)) {
 continue
 }
 
 $firstHeading = Get-FirstMarkdownHeading -Content $content
 if ([string]::IsNullOrWhiteSpace($firstHeading)) {
 continue
 }
 
 # Only consider headings that start with "Bug " as actual bugs
 if ($firstHeading -notmatch '^Bug\s+') {
 continue
 }
 
 # Check if bug is fixed (starts with "FIXED: Bug ")
 if ($firstHeading -match '^FIXED:\s+Bug\s+') {
 continue
 }
 
 if (-not (Test-ItemMatchesFilter -FileName $bugFile.Name -Title $firstHeading -Filter $Filter)) {
 continue
 }
 
 # This is an incomplete bug
 $relativePath = $bugFile.FullName.Substring($BasePath.Length + 1)
 $projectBugs += @{
 File = $relativePath
 Title = $firstHeading
 FullPath = $bugFile.FullName
 }
 $script:totalBugCount++
 } catch {
 # Skip files that can't be read
 Write-Host " Warning: Could not read $($bugFile.Name): $_" -ForegroundColor Yellow
 continue
 }
 }
 
 if ($projectBugs.Count -gt 0) {
 $script:allIncompleteBugs += @{
 Project = $ProjectName
 Bugs = $projectBugs
 }
 }
}

# Process root .tasks folder
$rootTasksFolder = Join-Path $BaseDir ".tasks"
Process-TasksFolder -TasksFolderPath $rootTasksFolder -ProjectName "(root)" -BasePath $BaseDir -Filter $Filter

# Process root .bugs folder
$rootBugsFolder = Join-Path $BaseDir ".bugs"
Process-BugsFolder -BugsFolderPath $rootBugsFolder -ProjectName "(root)" -BasePath $BaseDir -Filter $Filter

# Process all datrix projects
foreach ($project in $projects) {
 $tasksFolder = Join-Path $project.FullName ".tasks"
 Process-TasksFolder -TasksFolderPath $tasksFolder -ProjectName $project.Name -BasePath $project.FullName -Filter $Filter
 
 $bugsFolder = Join-Path $project.FullName ".bugs"
 Process-BugsFolder -BugsFolderPath $bugsFolder -ProjectName $project.Name -BasePath $project.FullName -Filter $Filter
}

# Display tasks results
if ($allIncompleteTasks.Count -gt 0) {
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "Incomplete Tasks" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host ""
 
 foreach ($projectData in $allIncompleteTasks) {
 Write-Host "=== $($projectData.Project) ===" -ForegroundColor Cyan
 
 foreach ($task in $projectData.Tasks) {
 Write-Host " $($task.FullPath)" -ForegroundColor White
 Write-Host " Title: $($task.Title)" -ForegroundColor Gray
 }
 
 Write-Host ""
 }
}

# Display bugs results
if ($allIncompleteBugs.Count -gt 0) {
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "Incomplete Bugs" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host ""
 
 foreach ($projectData in $allIncompleteBugs) {
 Write-Host "=== $($projectData.Project) ===" -ForegroundColor Cyan
 
 foreach ($bug in $projectData.Bugs) {
 Write-Host " $($bug.FullPath)" -ForegroundColor White
 Write-Host " Title: $($bug.Title)" -ForegroundColor Gray
 }
 
 Write-Host ""
 }
}

# Summary
Write-Host "========================================" -ForegroundColor Cyan
if ($totalTaskCount -eq 0 -and $totalBugCount -eq 0) {
 Write-Host "No incomplete tasks or bugs found!" -ForegroundColor Green
} else {
 if ($totalTaskCount -gt 0) {
 Write-Host "Total: $totalTaskCount incomplete task(s) across $($allIncompleteTasks.Count) project(s)" -ForegroundColor Cyan
 }
 if ($totalBugCount -gt 0) {
 Write-Host "Total: $totalBugCount incomplete bug(s) across $($allIncompleteBugs.Count) project(s)" -ForegroundColor Cyan
 }
 if ($totalTaskCount -gt 0 -and $totalBugCount -gt 0) {
 Write-Host "Grand Total: $($totalTaskCount + $totalBugCount) incomplete item(s)" -ForegroundColor Cyan
 }
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

exit 0
