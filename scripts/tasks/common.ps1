# Shared helpers for todo.ps1 and completed.ps1 (task/bug scanning).
# Do not run directly; dot-source from the caller script.

function Get-FirstMarkdownHeading {
 param(
 [string]$Content
 )
 if ([string]::IsNullOrWhiteSpace($Content)) {
 return $null
 }
 $lines = $Content -split "`r?`n"
 foreach ($line in $lines) {
 $trimmedLine = $line.Trim()
 if ($trimmedLine -match '^#+\s+(.+)$') {
 return $matches[1].Trim()
 }
 }
 return $null
}

function Test-ItemMatchesFilter {
 param(
 [string]$FileName,
 [string]$Title,
 [string]$Filter
 )
 if ([string]::IsNullOrWhiteSpace($Filter)) {
 return $true
 }
 return ($FileName -like "*$Filter*") -or ($Title -like "*$Filter*")
}
