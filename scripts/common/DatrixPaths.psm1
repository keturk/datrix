<#
.SYNOPSIS
 Common module for datrix workspace path and directory discovery

.DESCRIPTION
 Provides functions and variables for discovering datrix workspace paths and directories.
 Used by scripts in the datrix project to locate workspace root and repository directories.
#>

# Get the datrix workspace root directory
function Get-DatrixWorkspaceRoot {
 <#
 .SYNOPSIS
 Gets the datrix workspace root directory
 
 .DESCRIPTION
 Calculates the workspace root by navigating up from the script's location.
 Assumes scripts are in datrix\scripts\* and workspace root is the parent of datrix.
 
 .PARAMETER ScriptPath
 Optional path to the script. If not provided, uses the caller's script path.
 
 .EXAMPLE
 $workspaceRoot = Get-DatrixWorkspaceRoot
 #>
 [CmdletBinding()]
 param(
 [Parameter(Mandatory=$false)]
 [string]$ScriptPath
 )
 
 if (-not $ScriptPath) {
 # Try to get the caller's script path
 $caller = Get-PSCallStack | Select-Object -Skip 1 -First 1
 if ($caller.ScriptName) {
 $ScriptPath = $caller.ScriptName
 } else {
 # Fallback: use current script location
 $ScriptPath = $MyInvocation.PSCommandPath
 }
 }
 
 $scriptDir = Split-Path -Parent $ScriptPath
 
 # Get datrix root (scripts/* -> scripts -> datrix)
 $datrixRoot = Split-Path -Parent (Split-Path -Parent $scriptDir)
 
 # Get datrix workspace root (parent of datrix)
 $datrixWorkspaceRoot = Split-Path -Parent $datrixRoot
 
 return $datrixWorkspaceRoot
}

# Get the list of datrix repository directories
function Get-DatrixDirectories {
 <#
 .SYNOPSIS
 Gets the list of datrix repository directory names
 
 .DESCRIPTION
 Returns an array of directory names that should be searched in the workspace.
 
 .EXAMPLE
 $directories = Get-DatrixDirectories
 #>
 [CmdletBinding()]
 param()
 
 return @(
 "datrix",
 "datrix-cli",
 "datrix-common",
 "datrix-codegen-component",
 "datrix-codegen-python",
 "datrix-codegen-sql",
 "datrix-codegen-typescript",
 "datrix-language",
 "datrix-codegen-aws",
 "datrix-codegen-azure",
 "datrix-codegen-docker",
 "datrix-codegen-k8s",
 "datrix-projects"
 )
}

# Get full paths for all datrix directories
function Get-DatrixDirectoryPaths {
 <#
 .SYNOPSIS
 Gets full paths for all datrix repository directories
 
 .DESCRIPTION
 Returns an array of full directory paths that exist in the workspace.
 Only returns paths for directories that actually exist.
 
 .PARAMETER WorkspaceRoot
 Optional workspace root path. If not provided, will be calculated.
 
 .EXAMPLE
 $paths = Get-DatrixDirectoryPaths
 #>
 [CmdletBinding()]
 param(
 [Parameter(Mandatory=$false)]
 [string]$WorkspaceRoot
 )
 
 if (-not $WorkspaceRoot) {
 $WorkspaceRoot = Get-DatrixWorkspaceRoot
 }
 
 $directories = Get-DatrixDirectories
 $paths = @()
 
 foreach ($dir in $directories) {
 $dirPath = Join-Path $WorkspaceRoot $dir
 if (Test-Path $dirPath) {
 $paths += $dirPath
 }
 }
 
 return $paths
}

# Export functions
Export-ModuleMember -Function Get-DatrixWorkspaceRoot, Get-DatrixDirectories, Get-DatrixDirectoryPaths
