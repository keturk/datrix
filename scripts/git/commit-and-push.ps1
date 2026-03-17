<#
.SYNOPSIS
 Commits and pushes all Datrix repositories using messages from a JSON file.

.DESCRIPTION
 Reads commit messages from a JSON file (key = repo directory name, value = commit message).
 Sets global git user.email and user.name for commits, then deletes all .lock files under
 each repo's .git folder. Only repos that have an entry in the JSON are committed and pushed.
 Commit messages can be long and multi-line; they are passed to git via a temp file (-F).

.PARAMETER MessagesPath
 Optional. Path to the JSON file. Default: commit-messages.json (relative to current directory).
 Format: { "datrix": "message", "datrix-common": "message", ... }

.EXAMPLE
 .\commit-and-push.ps1
 Uses commit-messages.json in the current directory.

.EXAMPLE
 .\commit-and-push.ps1 commit-messages.json
.EXAMPLE
 .\commit-and-push.ps1 D:\datrix\commit-messages.json
#>
[CmdletBinding()]
param(
 [Parameter(Mandatory = $false, Position = 0)]
 [string]$MessagesPath = 'commit-messages.json',

 [switch]$Dbg
)

$ErrorActionPreference = 'Stop'

# Resolve path to messages file
if (-not (Test-Path -LiteralPath $MessagesPath)) {
 Write-Error "Messages file not found: $MessagesPath"
}
$MessagesPath = Resolve-Path -LiteralPath $MessagesPath

# Read and parse JSON; fail if invalid or not an object
$jsonText = Get-Content -LiteralPath $MessagesPath -Raw -Encoding UTF8
try {
 $messages = $jsonText | ConvertFrom-Json
} catch {
 Write-Error "Invalid JSON in messages file: $_"
}
if ($messages -isnot [PSCustomObject]) {
 Write-Error "Messages file root must be a JSON object (repo name -> message)."
}

# Navigate to workspace root and load repo list (common is under scripts, one level up from git)
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Join-Path $scriptPath ".."
$datrixCommon = Join-Path $scriptsDir "common\DatrixPaths.psm1"
if (-not (Test-Path $datrixCommon)) {
 Write-Error "DatrixPaths.psm1 not found at $datrixCommon"
}
Import-Module $datrixCommon -Force
$root = Get-DatrixWorkspaceRoot -ScriptPath $MyInvocation.MyCommand.Path
$repoPaths = Get-DatrixDirectoryPaths -WorkspaceRoot $root
Set-Location $root

# Ensure git user identity is set for commits
git config --global user.email "kercan@outlook.com"
git config --global user.name "Kamil Ercan Turkarslan"

# Ensure every repo key in the JSON exists in the workspace (fail fast)
$messageKeys = @($messages.PSObject.Properties | ForEach-Object { $_.Name })
$existingNames = @($repoPaths | ForEach-Object { Split-Path -Leaf $_ })
foreach ($key in $messageKeys) {
 if ($key -notin $existingNames) {
 Write-Error "Repo '$key' in messages file not found in workspace. Existing: $($existingNames -join ', ')"
 }
}

# Delete all .lock files under each repo's .git
foreach ($repoPath in $repoPaths) {
 $gitDir = Join-Path $repoPath '.git'
 if (-not (Test-Path $gitDir)) {
 Write-Host "$(Split-Path -Leaf $repoPath): no .git, skipping lock cleanup" -ForegroundColor Yellow
 continue
 }
 $locks = Get-ChildItem -Path $gitDir -Recurse -Filter '*.lock' -File -ErrorAction SilentlyContinue
 foreach ($f in $locks) {
 Remove-Item -LiteralPath $f.FullName -Force
 if ($Dbg) { Write-Host " Removed $($f.FullName)" -ForegroundColor Gray }
 }
}

# Commit and push only repos that have a message in the JSON
# Use .$repoName (not .PSObject.Properties[$repoName]); bracket index by name does not work on PSCustomObject
foreach ($repoPath in $repoPaths) {
 $repoName = Split-Path -Leaf $repoPath
 $message = $messages.$repoName
 if (-not $message) {
 Write-Host "${repoName}: no message in file, skipping" -ForegroundColor Yellow
 continue
 }
 if ([string]::IsNullOrWhiteSpace($message)) {
 Write-Host "${repoName}: empty message, skipping" -ForegroundColor Yellow
 continue
 }

 if (-not (Test-Path (Join-Path $repoPath '.git'))) {
 Write-Host "${repoName}: not a git repo, skipping" -ForegroundColor Yellow
 continue
 }

 Write-Host "Committing and pushing $repoName..." -ForegroundColor Cyan

 # Use temp file for message so long and multi-line descriptions work correctly
 $tempFile = [System.IO.Path]::GetTempFileName()
 try {
 [System.IO.File]::WriteAllText($tempFile, $message, [System.Text.UTF8Encoding]::new($false))
 git -C $repoPath add -A
 if ($LASTEXITCODE -ne 0) {
 Write-Host "${repoName}: git add failed with exit code $LASTEXITCODE" -ForegroundColor Red
 Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
 throw "Stopping on first git failure."
 }
 git -C $repoPath commit -F $tempFile
 $commitExit = $LASTEXITCODE
 if ($commitExit -eq 0) {
 git -C $repoPath push
 if ($LASTEXITCODE -ne 0) {
 Write-Host "${repoName}: git push failed with exit code $LASTEXITCODE" -ForegroundColor Red
 Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
 throw "Stopping on first git failure."
 }
 Write-Host "${repoName}: committed and pushed successfully" -ForegroundColor Green
 } elseif ($commitExit -eq 1) {
 Write-Host "${repoName}: nothing to commit (working tree clean)" -ForegroundColor Gray
 } else {
 Write-Host "${repoName}: git commit failed with exit code $commitExit" -ForegroundColor Red
 Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
 throw "Stopping on first git failure."
 }
 } finally {
 if (Test-Path -LiteralPath $tempFile) {
 Remove-Item -LiteralPath $tempFile -Force -ErrorAction SilentlyContinue
 }
 }
 Write-Host ""
}

Write-Host "Commit-and-push completed."
