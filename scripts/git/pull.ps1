[CmdletBinding()]
param(
 [switch]$Dbg
)

# Navigate to the datrix root directory (3 levels up from this script)
$scriptPath = Split-Path -Parent $MyInvocation.MyCommand.Path
$root = Resolve-Path (Join-Path $scriptPath "..\..\..")

Set-Location $root

Get-ChildItem -Directory | ForEach-Object {
 $repoPath = $_.FullName
 if (Test-Path (Join-Path $repoPath '.git')) {
 Write-Host "Pulling $($_.Name)..."
 try {
 git -C $repoPath pull
 if ($LASTEXITCODE -eq 0) {
 Write-Host "$($_.Name): pull completed successfully" -ForegroundColor Green
 } else {
 Write-Host "$($_.Name): pull failed with exit code $LASTEXITCODE" -ForegroundColor Red
 }
 } catch {
 Write-Host "$($_.Name): error during pull - $_" -ForegroundColor Red
 }
 Write-Host ""
 } else {
 Write-Host "$($_.Name): not a git repo, skipping" -ForegroundColor Yellow
 }
}

Write-Host "All pulls completed."

