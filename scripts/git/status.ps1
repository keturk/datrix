[CmdletBinding()]
param(
 [switch]$Detailed,
 [switch]$Dbg
)

# Navigate to the datrix root directory (3 levels up from this script)
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptPath "..\..\..")

Set-Location $root

Get-ChildItem -Directory | ForEach-Object {
 $repoPath = $_.FullName
 if (Test-Path (Join-Path $repoPath '.git')) {
 $status = git -C $repoPath status --porcelain
 if ([string]::IsNullOrWhiteSpace($status)) {
 Write-Host "$($_.Name): clean" -ForegroundColor Green
 } else {
 Write-Host "$($_.Name): has changes" -ForegroundColor Yellow

 if ($Detailed) {
 Write-Host " Details:" -ForegroundColor Cyan
 # Get branch information
 $branch = git -C $repoPath branch --show-current
 Write-Host " Branch: $branch" -ForegroundColor Gray

 # Get ahead/behind information
 $tracking = git -C $repoPath status --porcelain --branch | Select-Object -First 1
 if ($tracking -match '\[ahead (\d+)\]') {
 Write-Host " Ahead: $($matches[1]) commit(s)" -ForegroundColor Gray
 }
 if ($tracking -match '\[behind (\d+)\]') {
 Write-Host " Behind: $($matches[1]) commit(s)" -ForegroundColor Gray
 }

 # Show detailed status
 Write-Host " Changed files:" -ForegroundColor Gray
 git -C $repoPath status --short | ForEach-Object {
 Write-Host " $_" -ForegroundColor Gray
 }
 Write-Host ""
 }
 }
 } else {
 Write-Host "$($_.Name): not a git repo" -ForegroundColor DarkGray
 }
}

