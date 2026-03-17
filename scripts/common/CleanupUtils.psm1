<#
.SYNOPSIS
 Common module for cleanup utility functions

.DESCRIPTION
 Provides utility functions for cleanup scripts, including removing empty folders
 after deleting files and directories.
#>

function Remove-EmptyParentFolders {
 <#
 .SYNOPSIS
 Removes empty parent folders after deleting files or folders
 
 .DESCRIPTION
 After deleting a file or folder, this function walks up the directory tree
 and removes any empty parent folders. It stops at specified boundaries
 to prevent deleting important directories.
 
 .PARAMETER ItemPath
 The full path to the file or folder that was deleted
 
 .PARAMETER StopAtPath
 Optional path to stop at. The function will not remove folders at or above this path.
 If not specified, stops at the parent of ItemPath.
 
 .PARAMETER BaseDir
 Optional base directory. The function will not remove folders at or above this path.
 
 .EXAMPLE
 Remove-EmptyParentFolders -ItemPath "C:\project\.tasks\subfolder\file.md" -BaseDir "C:\project"
 #>
 [CmdletBinding()]
 param(
 [Parameter(Mandatory=$true)]
 [string]$ItemPath,
 
 [Parameter(Mandatory=$false)]
 [string]$StopAtPath,
 
 [Parameter(Mandatory=$false)]
 [string]$BaseDir
 )
 
 $parentFolder = Split-Path -Path $ItemPath -Parent
 
 if (-not $parentFolder -or -not (Test-Path $parentFolder)) {
 return
 }
 
 # Walk up the directory tree
 while ($parentFolder) {
 # Check if we should stop at this level
 $shouldStop = $false
 
 # Stop if we've reached the StopAtPath
 if ($StopAtPath) {
 try {
 $normalizedParent = [System.IO.Path]::GetFullPath($parentFolder).TrimEnd('\', '/')
 $normalizedStop = [System.IO.Path]::GetFullPath($StopAtPath).TrimEnd('\', '/')
 if ($normalizedParent -eq $normalizedStop) {
 $shouldStop = $true
 break
 }
 # Stop if we've gone above the stop path
 # If parent is NOT a child of stop path, we've gone above it
 $stopWithSeparator = $normalizedStop + [System.IO.Path]::DirectorySeparatorChar
 if (-not $normalizedParent.StartsWith($stopWithSeparator, [System.StringComparison]::OrdinalIgnoreCase) -and
 $normalizedParent -ne $normalizedStop) {
 $shouldStop = $true
 break
 }
 } catch {
 # Fallback to simple comparison
 if ($parentFolder -eq $StopAtPath) {
 $shouldStop = $true
 break
 }
 }
 }
 
 # Stop if we've reached the BaseDir
 if ($BaseDir) {
 try {
 $normalizedParent = [System.IO.Path]::GetFullPath($parentFolder).TrimEnd('\', '/')
 $normalizedBase = [System.IO.Path]::GetFullPath($BaseDir).TrimEnd('\', '/')
 if ($normalizedParent -eq $normalizedBase) {
 $shouldStop = $true
 break
 }
 } catch {
 # Fallback to simple comparison
 if ($parentFolder -eq $BaseDir) {
 $shouldStop = $true
 break
 }
 }
 }
 
 if ($shouldStop) {
 break
 }
 
 # Check if folder is empty and remove it
 try {
 $items = Get-ChildItem -Path $parentFolder -ErrorAction SilentlyContinue
 if ($null -eq $items -or $items.Count -eq 0) {
 Remove-Item -Path $parentFolder -Force -ErrorAction Stop
 Write-Host " Removed empty folder: $parentFolder" -ForegroundColor DarkGreen
 $parentFolder = Split-Path -Path $parentFolder -Parent
 } else {
 break
 }
 } catch {
 # Ignore errors when trying to remove parent folders
 break
 }
 }
}

function Confirm-YesNo {
 <#
 .SYNOPSIS
 Prompts the user for confirmation with yes/no and re-prompts on invalid input.

 .DESCRIPTION
 Displays "Are you sure? {yes/no}" and loops until the user enters "yes" or "no".
 Returns $true for "yes", $false for "no". Any other input triggers a re-prompt.

 .OUTPUTS
 [bool] $true if user confirmed with "yes", $false if user answered "no".
 #>
 [CmdletBinding()]
 param()

 do {
 $confirmation = (Read-Host "Are you sure? {yes/no}").Trim()
 if ($confirmation -ieq "yes") {
 return $true
 }
 if ($confirmation -ieq "no") {
 return $false
 }
 Write-Host "Please enter 'yes' or 'no'." -ForegroundColor Yellow
 } while ($true)
}

# Export functions
Export-ModuleMember -Function Remove-EmptyParentFolders, Confirm-YesNo
