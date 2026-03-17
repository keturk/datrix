# Get Latest Phase Number from .tasks Folders
# Scans all .tasks folders in datrix projects to find the highest phase number
# Returns only the phase number (no deletion, no other output)
# Usage: .\scripts\tasks\latest-phase.ps1 [-BaseDir <path>] [-Dbg]

[CmdletBinding()]
param(
 [string]$BaseDir = $(if ($PSScriptRoot) { Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot)) } else { "D:\datrix" }),
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Find all datrix projects
$projects = Get-ChildItem -Path $BaseDir -Directory | Where-Object { $_.Name -like "datrix*" }

$allPhaseNumbers = @()

# Function to collect phase numbers from a .tasks folder
function Get-PhaseNumbers {
 param(
 [string]$TasksFolderPath
 )
 
 if (-not (Test-Path $TasksFolderPath)) {
 return
 }
 
 # Find all phase-* directories
 $phaseDirs = Get-ChildItem -Path $TasksFolderPath -Directory -ErrorAction SilentlyContinue | Where-Object { $_.Name -match '^phase-\d+$' }
 
 # Handle case where Get-ChildItem returns a single object instead of an array
 if ($null -eq $phaseDirs) {
 return
 }
 if ($phaseDirs -isnot [System.Array]) {
 $phaseDirs = @($phaseDirs)
 }
 if ($phaseDirs.Count -eq 0) {
 return
 }
 
 foreach ($phaseDir in $phaseDirs) {
 # Extract phase number from folder name (e.g., "phase-01" -> 1)
 if ($phaseDir.Name -match '^phase-(\d+)$') {
 $phaseNumber = [int]$matches[1]
 if ($phaseNumber -notin $script:allPhaseNumbers) {
 $script:allPhaseNumbers += $phaseNumber
 }
 }
 }
}

# Process root .tasks folder
$rootTasksFolder = Join-Path $BaseDir ".tasks"
Get-PhaseNumbers -TasksFolderPath $rootTasksFolder

# Process all datrix projects
foreach ($project in $projects) {
 $tasksFolder = Join-Path $project.FullName ".tasks"
 Get-PhaseNumbers -TasksFolderPath $tasksFolder
}

# Return the latest phase number
if ($allPhaseNumbers.Count -eq 0) {
 if ($Dbg) {
 Write-Host "No phase folders found in .tasks directories." -ForegroundColor Yellow
 }
 exit 0
}

$latestPhase = ($allPhaseNumbers | Measure-Object -Maximum).Maximum

if ($Dbg) {
 Write-Host "Found phase numbers: $($allPhaseNumbers -join ', ')" -ForegroundColor Cyan
 Write-Host "Latest phase: $latestPhase" -ForegroundColor Green
} else {
 # Output only the phase number (for use in scripts)
 Write-Output $latestPhase
}

exit 0
