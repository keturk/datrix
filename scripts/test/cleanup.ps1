# Cleanup Test Results Folders
# Lists .test_results under each datrix-* project and under .generated (pruned walk), and lists files
# and subfolders inside each .test_results directory (same as legacy output).
# If -Force is provided, asks for confirmation before deletion.
# Usage: .\scripts\test\cleanup.ps1 [-BaseDir <path>] [-Force] [-Dbg]

[CmdletBinding()]
param(
 [string]$BaseDir = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))),
 [switch]$Force,
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$commonModulePath = Join-Path (Split-Path -Parent $PSScriptRoot) "common\CleanupUtils.psm1"
Import-Module $commonModulePath -Force

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

<#
 Pruned DFS under .generated:
 - At the .generated root only: collect any direct .test_results, and still recurse into every
   other subdirectory (python/, docker/, …). Otherwise finding .generated/.test_results would skip
   all nested generated projects.
 - Deeper: if a directory has a direct child .test_results, record it and do not recurse into sibling
   folders under that same directory (src/, build/, …).

 Limitation: if both project/.test_results and project/sub/.test_results exist, only the shallower
 path is found for that branch.
#>
function Get-TestResultsPathsUnderGeneratedPruned {
 param([string]$GeneratedRoot)
 $list = [System.Collections.ArrayList]@()
 $rootFull = [System.IO.Path]::GetFullPath($GeneratedRoot).TrimEnd('\', '/')

 function WalkGeneratedDir {
  param([string]$DirPath)
  if (-not (Test-Path -LiteralPath $DirPath)) {
   return
  }
  $children = @(Get-ChildItem -LiteralPath $DirPath -Directory -ErrorAction SilentlyContinue)
  if ($children.Count -eq 0) {
   return
  }

  $dirNorm = [System.IO.Path]::GetFullPath($DirPath).TrimEnd('\', '/')
  $isGeneratedRoot = ($dirNorm -eq $rootFull)

  if ($isGeneratedRoot) {
   foreach ($c in $children) {
    if ($c.Name -eq '.test_results') {
     $null = $list.Add($c.FullName)
    } else {
     WalkGeneratedDir -DirPath $c.FullName
    }
   }
   return
  }

  $directTestResults = $children | Where-Object { $_.Name -eq '.test_results' } | Select-Object -First 1
  if ($null -ne $directTestResults) {
   $null = $list.Add($directTestResults.FullName)
   return
  }
  foreach ($childDir in $children) {
   WalkGeneratedDir -DirPath $childDir.FullName
  }
 }

 WalkGeneratedDir -DirPath $rootFull
 return $list
}

$projects = Get-ChildItem -Path $BaseDir -Directory | Where-Object { $_.Name -like "datrix*" }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Test Results Cleanup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allTestResultsFolders = [System.Collections.ArrayList]@()

function Add-TestResultsFolder {
 param(
  [string]$TestResultsPath,
  [string]$ParentName
 )

 if (-not (Test-Path $TestResultsPath)) {
  return
 }

 $testResultsInfo = [PSCustomObject]@{
  Parent = $ParentName
  FullPath = $TestResultsPath
 }
 $null = $script:allTestResultsFolders.Add($testResultsInfo)
}

foreach ($project in $projects) {
 $testResultsFolder = Join-Path $project.FullName ".test_results"
 Add-TestResultsFolder -TestResultsPath $testResultsFolder -ParentName $project.Name
}

$generatedFolder = Join-Path $BaseDir ".generated"
if (Test-Path $generatedFolder) {
 $generatedFolderNorm = [System.IO.Path]::GetFullPath($generatedFolder).TrimEnd('\', '/')
 foreach ($fullPath in (Get-TestResultsPathsUnderGeneratedPruned -GeneratedRoot $generatedFolder)) {
  $parentFull = [System.IO.Path]::GetFullPath([System.IO.Path]::GetDirectoryName($fullPath)).TrimEnd('\', '/')
  $parentRelative = if ($parentFull -eq $generatedFolderNorm) { "." } else { $parentFull.Substring($generatedFolderNorm.Length).TrimStart('\', '/') }
  $parentName = if ($parentRelative -eq ".") { ".generated" } else { ".generated\$parentRelative" }
  Add-TestResultsFolder -TestResultsPath $fullPath -ParentName $parentName
 }
}

if ($allTestResultsFolders.Count -eq 0) {
 Write-Host "No .test_results folders found." -ForegroundColor Green
 Write-Host ""
 exit 0
}

Write-Host "Found $($allTestResultsFolders.Count) .test_results folder(s)." -ForegroundColor Cyan
Write-Host ""

$groupedByParent = $allTestResultsFolders | Group-Object -Property Parent

foreach ($group in $groupedByParent) {
 Write-Host "=== $($group.Name) ===" -ForegroundColor Cyan
 foreach ($folder in $group.Group) {
  Write-Host " .test_results" -ForegroundColor White
  Write-Host " $($folder.FullPath)" -ForegroundColor Gray

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

if ($Force) {
 Write-Host "========================================" -ForegroundColor Yellow
 Write-Host "WARNING: You are about to delete ALL $($allTestResultsFolders.Count) .test_results folder(s)" -ForegroundColor Yellow
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

 foreach ($folder in $allTestResultsFolders) {
  try {
   Remove-Item -Path $folder.FullPath -Recurse -Force -ErrorAction Stop
   Write-Host " Deleted: $($folder.FullPath)" -ForegroundColor Green
   $deletedCount++

   Remove-EmptyParentFolders -ItemPath $folder.FullPath -BaseDir $BaseDir
  } catch {
   Write-Host " Error deleting $($folder.FullPath): $_" -ForegroundColor Red
   $errorCount++
  }
 }

 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 if ($errorCount -eq 0) {
  Write-Host "Successfully deleted $deletedCount folder(s)." -ForegroundColor Green
 } else {
  Write-Host "Deleted $deletedCount folder(s), $errorCount error(s)" -ForegroundColor Yellow
 }
 Write-Host "========================================" -ForegroundColor Cyan
} else {
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "To delete these folders, run with -Force parameter" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Gray
 Write-Host " .\scripts\test\cleanup.ps1 -Force" -ForegroundColor Gray
 Write-Host "========================================" -ForegroundColor Cyan
}

Write-Host ""

exit 0
