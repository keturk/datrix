# Cleanup Temporary Cache Folders
# Lists cache folders and files under the monorepo root ($BaseDir) and in all datrix* projects (recursive). Root: direct children only; projects: full recursion (skips .git, .venv, node_modules, .generated; does not scan inside .generated). Folders: .hypothesis, .ruff_cache, .ruff_check, .mypy_cache, .pytest_cache, htmlcov, .benchmarks, __pycache__, .tox, .nox, .cache, .pyre, .pytype, cython_debug. Files: .coverage, .coverage.*, coverage.xml, .dmypy.json, dmypy.json.
# If -Force parameter is provided, asks for confirmation before deletion
# Usage: .\scripts\dev\cleanup_temps.ps1 [-BaseDir <path>] [-Force] [-AdditionalFolders <string[]>] [-Dbg]

[CmdletBinding()]
param(
 [string]$BaseDir = (Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $PSScriptRoot))),
 [switch]$Force,
 [string[]]$AdditionalFolders = @(),
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"

# Import common cleanup utilities
$commonModulePath = Join-Path (Split-Path -Parent $PSScriptRoot) "common\CleanupUtils.psm1"
Import-Module $commonModulePath -Force

# Default cache folders to clean up
$defaultCacheFolders = @(
 ".hypothesis",
 ".ruff_cache",
 ".ruff_check",
 ".mypy_cache",
 ".pytest_cache",
 "htmlcov",
 ".benchmarks",
 "__pycache__",
 ".tox",
 ".nox",
 ".cache",
 ".pyre",
 ".pytype",
 "cython_debug"
)

# Default cache files to clean up
$defaultCacheFiles = @(
 ".coverage",
 "coverage.xml",
 ".dmypy.json",
 "dmypy.json"
)

# Default cache file patterns (glob) to clean up (matched at project root)
$defaultCacheFilePatterns = @(
 ".coverage.*"
)

# Folders to preserve (do not clean up)
$preserveFolders = @(
 ".test_results",
 ".tasks"
)

# Directories to skip when recursing (avoid scanning .git, venvs, etc.)
$skipRecurseDirs = @(
 ".git",
 ".venv",
 "venv",
 "env",
 "node_modules",
 ".generated"
)

# Combine default and additional folders
$allCacheFolders = $defaultCacheFolders + $AdditionalFolders
$allCacheFiles = $defaultCacheFiles
$allCacheFilePatterns = $defaultCacheFilePatterns

# Find all datrix projects
$projects = Get-ChildItem -Path $BaseDir -Directory | Where-Object { $_.Name -like "datrix*" }

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "Temporary Cache Cleanup" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

$allCacheItemsFound = [System.Collections.ArrayList]@()
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


# Function to collect cache folders
function Get-CacheFolders {
 param(
 [string]$CacheFolderPath,
 [string]$CacheFolderName,
 [string]$ParentName
 )

 if (-not (Test-Path $CacheFolderPath)) {
 return
 }

 # Skip preserved folders
 if ($preserveFolders -contains $CacheFolderName) {
 return
 }

 $item = Get-Item -Path $CacheFolderPath -ErrorAction SilentlyContinue
 if ($null -eq $item) {
 return
 }

 if ($item.PSIsContainer) {
 $size = Get-FolderSize -Path $CacheFolderPath
 } else {
 $size = $item.Length
 }
 $script:totalSize += $size

 $cacheItemInfo = [PSCustomObject]@{
 Parent = $ParentName
 Name = $CacheFolderName
 FullPath = $CacheFolderPath
 Size = $size
 IsDirectory = $item.PSIsContainer
 }
 $null = $script:allCacheItemsFound.Add($cacheItemInfo)
}

# Function to collect cache files
function Get-CacheFiles {
 param(
 [string]$CacheFilePath,
 [string]$CacheFileName,
 [string]$ParentName
 )

 if (-not (Test-Path $CacheFilePath)) {
 return
 }

 $item = Get-Item -Path $CacheFilePath -ErrorAction SilentlyContinue
 if ($null -eq $item -or $item.PSIsContainer) {
 return
 }

 $size = $item.Length
 $script:totalSize += $size

 $cacheFileInfo = [PSCustomObject]@{
 Parent = $ParentName
 Name = $CacheFileName
 FullPath = $CacheFilePath
 Size = $size
 IsDirectory = $false
 }
 $null = $script:allCacheItemsFound.Add($cacheFileInfo)
}

# Recursively find cache folders under a root (skips $skipRecurseDirs and cache-named dirs)
function Get-CacheFoldersUnder {
 param(
 [string]$Root,
 [string]$ParentName
 )

 $dirs = Get-ChildItem -Path $Root -Directory -Force -ErrorAction SilentlyContinue
 foreach ($d in $dirs) {
 if ($allCacheFolders -contains $d.Name) {
 if ($preserveFolders -notcontains $d.Name) {
 Get-CacheFolders -CacheFolderPath $d.FullName -CacheFolderName $d.Name -ParentName $ParentName
 }
 }
 elseif ($skipRecurseDirs -notcontains $d.Name) {
 Get-CacheFoldersUnder -Root $d.FullName -ParentName $ParentName
 }
 }
}

# Recursively find cache files under a root (skips $skipRecurseDirs)
function Get-CacheFilesUnder {
 param(
 [string]$Root,
 [string]$ParentName
 )

 $dirs = Get-ChildItem -Path $Root -Directory -Force -ErrorAction SilentlyContinue
 foreach ($d in $dirs) {
 if ($skipRecurseDirs -contains $d.Name) {
 continue
 }
 Get-CacheFilesUnder -Root $d.FullName -ParentName $ParentName
 }
 $files = Get-ChildItem -Path $Root -File -Force -ErrorAction SilentlyContinue
 foreach ($f in $files) {
 if ($allCacheFiles -contains $f.Name) {
 Get-CacheFiles -CacheFilePath $f.FullName -CacheFileName $f.Name -ParentName $ParentName
 }
 else {
 foreach ($pattern in $allCacheFilePatterns) {
 if ($f.Name -like $pattern) {
 Get-CacheFiles -CacheFilePath $f.FullName -CacheFileName $f.Name -ParentName $ParentName
 break
 }
 }
 }
 }
 }

# Process monorepo root (cache folders and files directly under $BaseDir, e.g. d:\datrix\.pytest_cache)
$baseDirName = (Get-Item -Path $BaseDir -ErrorAction SilentlyContinue).Name
if ($baseDirName) {
 foreach ($cacheFolder in $allCacheFolders) {
 $cacheFolderPath = Join-Path $BaseDir $cacheFolder
 Get-CacheFolders -CacheFolderPath $cacheFolderPath -CacheFolderName $cacheFolder -ParentName $baseDirName
 }
 foreach ($cacheFile in $allCacheFiles) {
 $cacheFilePath = Join-Path $BaseDir $cacheFile
 Get-CacheFiles -CacheFilePath $cacheFilePath -CacheFileName $cacheFile -ParentName $baseDirName
 }
 foreach ($pattern in $allCacheFilePatterns) {
 Get-ChildItem -Path $BaseDir -Filter $pattern -File -ErrorAction SilentlyContinue | ForEach-Object {
 Get-CacheFiles -CacheFilePath $_.FullName -CacheFileName $_.Name -ParentName $baseDirName
 }
 }
}

# Process all datrix projects (recursive under each project root)
foreach ($project in $projects) {
 Get-CacheFoldersUnder -Root $project.FullName -ParentName $project.Name
 Get-CacheFilesUnder -Root $project.FullName -ParentName $project.Name
}

# Display all cache items
if ($allCacheItemsFound.Count -eq 0) {
 Write-Host "No cache items found." -ForegroundColor Green
 Write-Host ""
 exit 0
}

Write-Host "Found $($allCacheItemsFound.Count) cache item(s) (Total: $(Format-Size $totalSize)):" -ForegroundColor Cyan
Write-Host ""

# Group by parent for display
$groupedByParent = $allCacheItemsFound | Group-Object -Property Parent

foreach ($group in $groupedByParent) {
 Write-Host "=== $($group.Name) ===" -ForegroundColor Cyan
 foreach ($folder in $group.Group) {
 Write-Host " $($folder.Name) ($(Format-Size $folder.Size))" -ForegroundColor White
 Write-Host " $($folder.FullPath)" -ForegroundColor Gray
 }
 Write-Host ""
}

# If -Force is provided, ask for confirmation and delete
if ($Force) {
 Write-Host "========================================" -ForegroundColor Yellow
 Write-Host "WARNING: You are about to delete ALL $($allCacheItemsFound.Count) cache item(s)" -ForegroundColor Yellow
 Write-Host " Total size: $(Format-Size $totalSize)" -ForegroundColor Yellow
 Write-Host "========================================" -ForegroundColor Yellow
 Write-Host ""

 if (-not (Confirm-YesNo)) {
 Write-Host ""
 Write-Host "Deletion cancelled." -ForegroundColor Yellow
 exit 0
 }

 Write-Host ""
 Write-Host "Deleting cache items..." -ForegroundColor Yellow

 $deletedCount = 0
 $errorCount = 0
 $deletedSize = 0

 foreach ($item in $allCacheItemsFound) {
 try {
 if ($item.IsDirectory) {
 Remove-Item -Path $item.FullPath -Recurse -Force -ErrorAction Stop
 # Remove empty parent folders
 Remove-EmptyParentFolders -ItemPath $item.FullPath -BaseDir $BaseDir
 } else {
 Remove-Item -Path $item.FullPath -Force -ErrorAction Stop
 }
 Write-Host " Deleted: $($item.FullPath)" -ForegroundColor Green
 $deletedCount++
 $deletedSize += $item.Size
 } catch {
 Write-Host " Error deleting $($item.FullPath): $_" -ForegroundColor Red
 $errorCount++
 }
 }

 Write-Host ""
 Write-Host "========================================" -ForegroundColor Cyan
 if ($errorCount -eq 0) {
 Write-Host "Successfully deleted $deletedCount item(s) ($(Format-Size $deletedSize))" -ForegroundColor Green
 } else {
 Write-Host "Deleted $deletedCount item(s), $errorCount error(s)" -ForegroundColor Yellow
 }
 Write-Host "========================================" -ForegroundColor Cyan
} else {
 Write-Host "========================================" -ForegroundColor Cyan
 Write-Host "To delete these items, run with -Force parameter" -ForegroundColor Cyan
 Write-Host ""
 Write-Host "Usage:" -ForegroundColor Gray
 Write-Host " .\scripts\dev\cleanup_temps.ps1 -Force # Delete all cache folders and files" -ForegroundColor Gray
 Write-Host " .\scripts\dev\cleanup_temps.ps1 -Force -AdditionalFolders \".coverage\",\"__pycache__\" # Delete cache items plus additional ones" -ForegroundColor Gray
 Write-Host "========================================" -ForegroundColor Cyan
}

Write-Host ""

exit 0
