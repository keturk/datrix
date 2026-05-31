# List Completed Tasks and Fixed Bugs from .tasks and .bugs Folders
# Scans all datrix projects for completed tasks (those with "COMPLETED: " prefix)
# and fixed bugs (those with "FIXED: " prefix)
# Usage: .\scripts\tasks\completed.ps1 [-BaseDir <path>] [-Filter <string>] [-Dbg]
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


$allCompletedTasks = @()
$allCompletedBugs = @()
$totalTaskCount = 0
$totalBugCount = 0

# Build a phase status index across all datrix projects so root phase dependencies
# can reflect completion state even when the phase folder only contains dependencies.md.
function Build-PhaseTaskStatusIndex {
 param(
 [string[]]$TasksRoots
 )

 $index = @{}

 foreach ($tasksRoot in $TasksRoots) {
 if (-not (Test-Path $tasksRoot)) {
 continue
 }

 $phaseFolders = Get-ChildItem -Path $tasksRoot -Directory -Filter "phase-*" -ErrorAction SilentlyContinue
 if ($null -eq $phaseFolders) {
 continue
 }
 if ($phaseFolders -isnot [System.Array]) {
 $phaseFolders = @($phaseFolders)
 }

 foreach ($phaseFolder in $phaseFolders) {
 if (-not $index.ContainsKey($phaseFolder.Name)) {
 $index[$phaseFolder.Name] = @{ Total = 0; Completed = 0 }
 }

 $taskFiles = Get-ChildItem -Path $phaseFolder.FullName -Filter "task-*.md" -Recurse -File -ErrorAction SilentlyContinue
 if ($null -eq $taskFiles) {
 continue
 }
 if ($taskFiles -isnot [System.Array]) {
 $taskFiles = @($taskFiles)
 }

 foreach ($taskFile in $taskFiles) {
 try {
 $content = Get-Content -Path $taskFile.FullName -Raw -ErrorAction Stop
 $firstHeading = Get-FirstMarkdownHeading -Content $content
 if ([string]::IsNullOrWhiteSpace($firstHeading)) {
 continue
 }

 $index[$phaseFolder.Name].Total++
 if ($firstHeading -match '^COMPLETED:\s+') {
 $index[$phaseFolder.Name].Completed++
 }
 } catch {
 continue
 }
 }
 }
 }

 return $index
}

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
 
 # Find only task-prefixed markdown files recursively
 $taskFiles = Get-ChildItem -Path $TasksFolderPath -Filter "task-*.md" -Recurse -File -ErrorAction SilentlyContinue

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
 
 # Consider task headings: "Task ..." or "COMPLETED: Task ..."
 if ($firstHeading -notmatch '^(COMPLETED:\s+)?Task\s+') {
 continue
 }
 
 # Only include completed tasks (starts with "COMPLETED: Task ")
 if ($firstHeading -notmatch '^COMPLETED:\s+Task\s') {
 continue
 }
 
 if (-not (Test-ItemMatchesFilter -FileName $taskFile.Name -Title $firstHeading -Filter $Filter)) {
 continue
 }
 
 # This is a completed task
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
 $script:allCompletedTasks += @{
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
 
 # Find only task-prefixed markdown files recursively
 $bugFiles = Get-ChildItem -Path $BugsFolderPath -Filter "task-*.md" -Recurse -File -ErrorAction SilentlyContinue

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
 
 # Consider bug headings: "Bug ..." or "FIXED: Bug ..."
 if ($firstHeading -notmatch '^(FIXED:\s+)?Bug\s+') {
 continue
 }
 
 # Only include fixed bugs (starts with "FIXED: Bug ")
 if ($firstHeading -notmatch '^FIXED:\s+Bug\s+') {
 continue
 }
 
 if (-not (Test-ItemMatchesFilter -FileName $bugFile.Name -Title $firstHeading -Filter $Filter)) {
 continue
 }
 
 # This is a fixed bug
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
 $script:allCompletedBugs += @{
 Project = $ProjectName
 Bugs = $projectBugs
 }
 }
}

# Function to process phase dependencies (completed phases only)
function Process-CompletedPhaseDependencies {
 param(
 [string]$PhasesBasePath,
 [string]$BasePath,
 [string]$ProjectName,
 [hashtable]$PhaseTaskStatusIndex,
 [string]$Filter = ""
 )

 if (-not (Test-Path $PhasesBasePath)) {
 return
 }

 # Find all phase-* folders
 $phaseFolders = Get-ChildItem -Path $PhasesBasePath -Directory -Filter "phase-*" -ErrorAction SilentlyContinue

 if ($null -eq $phaseFolders) {
 return
 }
 if ($phaseFolders -isnot [System.Array]) {
 $phaseFolders = @($phaseFolders)
 }
 if ($phaseFolders.Count -eq 0) {
 return
 }

 $completedPhaseDependencies = @()

 foreach ($phaseFolder in $phaseFolders) {
 $dependenciesFile = Join-Path $phaseFolder.FullName "dependencies.md"

 if (-not (Test-Path $dependenciesFile)) {
 continue
 }

 # Find all task-*.md files in this phase (including nested folders)
 $taskFiles = Get-ChildItem -Path $phaseFolder.FullName -Filter "task-*.md" -Recurse -File -ErrorAction SilentlyContinue

 $completedCount = 0
 $totalCount = 0

 if ($null -ne $taskFiles) {
 if ($taskFiles -isnot [System.Array]) {
 $taskFiles = @($taskFiles)
 }

 foreach ($taskFile in $taskFiles) {
 try {
 $content = Get-Content -Path $taskFile.FullName -Raw -ErrorAction Stop
 $firstHeading = Get-FirstMarkdownHeading -Content $content

 if ($null -ne $firstHeading) {
 $totalCount++

 # Check if it's completed (starts with "COMPLETED: ")
 if ($firstHeading -match '^COMPLETED:\s+') {
 $completedCount++
 }
 }
 } catch {
 # Skip files that can't be read
 continue
 }
 }
 }

 # If no local tasks were found, fall back to cross-project phase status.
 if ($totalCount -eq 0 -and $null -ne $PhaseTaskStatusIndex -and $PhaseTaskStatusIndex.ContainsKey($phaseFolder.Name)) {
 $totalCount = [int]$PhaseTaskStatusIndex[$phaseFolder.Name].Total
 $completedCount = [int]$PhaseTaskStatusIndex[$phaseFolder.Name].Completed
 }

 # If ALL tasks are completed, show the dependencies
 if ($totalCount -gt 0 -and $completedCount -eq $totalCount) {
 $relativePath = $dependenciesFile.Substring($BasePath.Length + 1)
 if (Test-ItemMatchesFilter -FileName (Split-Path -Leaf $dependenciesFile) -Title $phaseFolder.Name -Filter $Filter) {
 $completedPhaseDependencies += @{
 PhaseFolder = $phaseFolder.Name
 DependenciesFile = $relativePath
 FullPath = $dependenciesFile
 CompletedTaskCount = $completedCount
 TotalTaskCount = $totalCount
 }
 }
 }
 }

 if ($completedPhaseDependencies.Count -gt 0) {
 # Check if we already have an entry for this project
 $existingProject = $null
 foreach ($projectData in $script:allCompletedTasks) {
 if ($projectData.Project -eq $ProjectName) {
 $existingProject = $projectData
 break
 }
 }

 if ($null -ne $existingProject) {
 # Add to existing project
 $existingProject.PhaseDependencies = $completedPhaseDependencies
 } else {
 # Create new project entry
 $script:allCompletedTasks += @{
 Project = $ProjectName
 PhaseDependencies = $completedPhaseDependencies
 Tasks = @()
 }
 }
 }
}

# Process root .tasks folder
$rootTasksFolder = Join-Path $BaseDir ".tasks"
$phaseTasksRoots = @($rootTasksFolder)
foreach ($project in $projects) {
 $phaseTasksRoots += (Join-Path $project.FullName ".tasks")
}
$phaseTaskStatusIndex = Build-PhaseTaskStatusIndex -TasksRoots $phaseTasksRoots

Process-TasksFolder -TasksFolderPath $rootTasksFolder -ProjectName "(root)" -BasePath $BaseDir -Filter $Filter
Process-CompletedPhaseDependencies -PhasesBasePath $rootTasksFolder -BasePath $BaseDir -ProjectName "(root)" -PhaseTaskStatusIndex $phaseTaskStatusIndex -Filter $Filter

# Process root .bugs folder
$rootBugsFolder = Join-Path $BaseDir ".bugs"
Process-BugsFolder -BugsFolderPath $rootBugsFolder -ProjectName "(root)" -BasePath $BaseDir -Filter $Filter

# Process all datrix projects
foreach ($project in $projects) {
 $tasksFolder = Join-Path $project.FullName ".tasks"
 Process-TasksFolder -TasksFolderPath $tasksFolder -ProjectName $project.Name -BasePath $project.FullName -Filter $Filter
 Process-CompletedPhaseDependencies -PhasesBasePath $tasksFolder -BasePath $project.FullName -ProjectName $project.Name -PhaseTaskStatusIndex $phaseTaskStatusIndex -Filter $Filter

 $bugsFolder = Join-Path $project.FullName ".bugs"
 Process-BugsFolder -BugsFolderPath $bugsFolder -ProjectName $project.Name -BasePath $project.FullName -Filter $Filter
}

# Display tasks results
if ($allCompletedTasks.Count -gt 0) {
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "Completed Tasks" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host ""

 foreach ($projectData in $allCompletedTasks) {
 Write-Host "=== $($projectData.Project) ===" -ForegroundColor Cyan

 # Display phase dependencies first if they exist
 if ($null -ne $projectData.PhaseDependencies -and $projectData.PhaseDependencies.Count -gt 0) {
 foreach ($phaseDep in $projectData.PhaseDependencies) {
 Write-Host "   $($phaseDep.FullPath)" -ForegroundColor White
 if ($null -ne $phaseDep.TotalTaskCount) {
 Write-Host "   Phase: $($phaseDep.PhaseFolder) | Completed Tasks: $($phaseDep.CompletedTaskCount)/$($phaseDep.TotalTaskCount)" -ForegroundColor Gray
 } else {
 Write-Host "   Phase: $($phaseDep.PhaseFolder)" -ForegroundColor Gray
 }
 }
 if ($projectData.Tasks.Count -gt 0) {
 Write-Host ""
 }
 }

 # Display regular tasks
 if ($null -ne $projectData.Tasks -and $projectData.Tasks.Count -gt 0) {
 foreach ($task in $projectData.Tasks) {
 Write-Host "   $($task.FullPath)" -ForegroundColor White
 Write-Host "   Title: $($task.Title)" -ForegroundColor Gray
 }
 }

 Write-Host ""
 }
}

# Display bugs results
if ($allCompletedBugs.Count -gt 0) {
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "Fixed Bugs" -ForegroundColor Cyan
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host ""
 
 foreach ($projectData in $allCompletedBugs) {
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
 Write-Host "No completed tasks or fixed bugs found!" -ForegroundColor Green
} else {
 if ($totalTaskCount -gt 0) {
 Write-Host "Total: $totalTaskCount completed task(s) across $($allCompletedTasks.Count) project(s)" -ForegroundColor Cyan
 }
 if ($totalBugCount -gt 0) {
 Write-Host "Total: $totalBugCount fixed bug(s) across $($allCompletedBugs.Count) project(s)" -ForegroundColor Cyan
 }
 if ($totalTaskCount -gt 0 -and $totalBugCount -gt 0) {
 Write-Host "Grand Total: $($totalTaskCount + $totalBugCount) completed item(s)" -ForegroundColor Cyan
 }
}
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

