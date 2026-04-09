# Report generation status from the latest generate-results-*.log file.
# Finds the latest timestamped log under the results directory (default:
# <workspace>\.generated\.results) and lists which projects succeeded and failed.
# Use -ResultsDir when generate.ps1 wrote logs next to a custom output path or -OutputBase.

[CmdletBinding()]
param(
 # Relative to workspace root, or an absolute path. Example: .projects\curvaero\python\.results
 [string]$ResultsDir = ""
)

$ErrorActionPreference = "Stop"

# Script is under datrix\scripts\dev; workspace root is three levels up
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$WorkspaceRoot = Split-Path -Parent (Split-Path -Parent (Split-Path -Parent $ScriptDir))
$resolvedResultsDir = if ([string]::IsNullOrWhiteSpace($ResultsDir)) {
 Join-Path $WorkspaceRoot ".generated\.results"
} elseif ([System.IO.Path]::IsPathRooted($ResultsDir)) {
 $ResultsDir
} else {
 [System.IO.Path]::GetFullPath((Join-Path $WorkspaceRoot $ResultsDir))
}

# Pattern: [N/M] project-name: Success|Failed
$StatusLinePattern = '^\s*\[(\d+)/(\d+)\]\s+([^:]+):\s+(Success|Failed)\s*$'

function Get-LatestGenerateResultsLog {
 if (-not (Test-Path $resolvedResultsDir)) {
 Write-Error "Results directory not found: $resolvedResultsDir"
 exit 1
 }
 $logs = Get-ChildItem -Path $resolvedResultsDir -Filter "generate-results-*.log" -File -ErrorAction SilentlyContinue
 if (-not $logs) {
 Write-Error "No generate-results-*.log files found in $resolvedResultsDir"
 exit 1
 }
 # Filename format: generate-results-YYYYMMDD-HHMMSS.log -> sort by name = chronological
 $latest = $logs | Sort-Object Name -Descending | Select-Object -First 1
 return $latest
}

function Parse-GenerationLog {
 param([System.IO.FileInfo]$LogFile)
 $succeeded = [System.Collections.Generic.List[string]]::new()
 $failed = [System.Collections.Generic.List[string]]::new()
 $totalExpected = $null
 $timestamp = $null

 $content = Get-Content -Path $LogFile.FullName -Encoding UTF8
 foreach ($line in $content) {
 if ($timestamp -eq $null -and $line -match '^Timestamp:\s+(.+)$') {
 $timestamp = $matches[1].Trim()
 }
 if ($line -match $StatusLinePattern) {
 $current = [int]$matches[1]
 $totalExpected = [int]$matches[2]
 $projectName = $matches[3].Trim()
 $status = $matches[4]
 if ($status -eq "Success") {
 $succeeded.Add($projectName)
 } else {
 $failed.Add($projectName)
 }
 }
 }
 return @{
 LogPath = $LogFile.FullName
 Timestamp = $timestamp
 Succeeded = $succeeded
 Failed = $failed
 TotalExpected = $totalExpected
 }
}

function Write-StatusReport {
 param($Result)
 $useColor = $Host.UI.RawUI -and (Get-Command Write-Host).Parameters.ContainsKey("ForegroundColor")
 $green = if ($useColor) { "Green" } else { $null }
 $red = if ($useColor) { "Red" } else { $null }
 $cyan = if ($useColor) { "Cyan" } else { $null }
 $gray = if ($useColor) { "DarkGray" } else { $null }

 $sep = "=" * 80
 Write-Host $sep
 if ($cyan) { Write-Host "GENERATION STATUS REPORT" -ForegroundColor $cyan } else { Write-Host "GENERATION STATUS REPORT" }
 Write-Host $sep
 Write-Host ""
 Write-Host "Log file: $($Result.LogPath)"
 if ($Result.Timestamp) {
 if ($gray) { Write-Host "Timestamp: $($Result.Timestamp)" -ForegroundColor $gray } else { Write-Host "Timestamp: $($Result.Timestamp)" }
 }
 if ($Result.TotalExpected -ne $null) {
 Write-Host "Projects in log: $($Result.Succeeded.Count + $Result.Failed.Count) / $($Result.TotalExpected)"
 }
 Write-Host ""

 if ($Result.Succeeded.Count -gt 0) {
 if ($green) { Write-Host "SUCCEEDED ($($Result.Succeeded.Count))" -ForegroundColor $green } else { Write-Host "SUCCEEDED ($($Result.Succeeded.Count))" }
 foreach ($name in $Result.Succeeded) {
 if ($green) { Write-Host " [OK] $name" -ForegroundColor $green } else { Write-Host " [OK] $name" }
 }
 Write-Host ""
 }

 if ($Result.Failed.Count -gt 0) {
 if ($red) { Write-Host "FAILED ($($Result.Failed.Count))" -ForegroundColor $red } else { Write-Host "FAILED ($($Result.Failed.Count))" }
 foreach ($name in $Result.Failed) {
 if ($red) { Write-Host " [X] $name" -ForegroundColor $red } else { Write-Host " [X] $name" }
 }
 Write-Host ""
 }

 Write-Host $sep
 if ($cyan) { Write-Host "SUMMARY" -ForegroundColor $cyan } else { Write-Host "SUMMARY" }
 Write-Host $sep
 Write-Host "Succeeded: $($Result.Succeeded.Count)"
 Write-Host "Failed: $($Result.Failed.Count)"
 if ($Result.TotalExpected -ne $null) {
 $pending = $Result.TotalExpected - $Result.Succeeded.Count - $Result.Failed.Count
 if ($pending -gt 0) {
 Write-Host "Pending: $pending (run may still be in progress)"
 }
 }
 Write-Host $sep
}

try {
 $logFile = Get-LatestGenerateResultsLog
 $result = Parse-GenerationLog -LogFile $logFile
 Write-StatusReport -Result $result
 if ($result.Failed.Count -gt 0) {
 exit 1
 }
 exit 0
} catch {
 Write-Error $_
 exit 1
}
