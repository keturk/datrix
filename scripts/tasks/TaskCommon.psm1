<#
.SYNOPSIS
 Shared helpers for todo.ps1 and completed.ps1 (task/bug scanning).
#>

function Get-FirstMarkdownHeading {
 <#
 .SYNOPSIS
 The text of the first Markdown heading in Content, or $null when there is none.
 #>
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
 <#
 .SYNOPSIS
 True when Filter is empty, or the file name or title contains it.
 #>
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

Export-ModuleMember -Function Get-FirstMarkdownHeading, Test-ItemMatchesFilter
