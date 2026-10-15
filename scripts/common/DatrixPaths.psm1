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
 Gets the datrix workspace root directory (the parent of the datrix showcase repo).

 .DESCRIPTION
 Derived from this module's own location, which is fixed (scripts\common\DatrixPaths.psm1):
 common -> scripts -> datrix -> workspace. The same anchoring rule as
 common\lib\datrix_scripts\paths.py (WORKSPACE_DIR), so a script's own depth never matters.

 .EXAMPLE
 $workspaceRoot = Get-DatrixWorkspaceRoot
 #>
 [CmdletBinding()]
 [OutputType([string])]
 param()

 $scriptsDir = Split-Path -Parent $PSScriptRoot
 $showcaseDir = Split-Path -Parent $scriptsDir
 return (Split-Path -Parent $showcaseDir)
}

# Get the list of datrix repository directories
function Get-DatrixDirectories {
 <#
 .SYNOPSIS
 Gets the list of datrix repository directory names

 .DESCRIPTION
 Discovers the repositories on disk rather than hardcoding them: the datrix showcase repo
 first (it is the anchor every script resolves paths from), then every "datrix-*" package
 directory in the workspace, sorted.

 Discovery is deliberate. Datrix is a multi-language, multi-platform generator, so a new
 datrix-codegen-<lang> package must never require an edit here to become visible to the
 dev scripts that consume this list (file-count, syntax-checker, datrix-format,
 check-debug-artifacts, config-linter, compile, duplicate -Mono).

 .PARAMETER WorkspaceRoot
 Monorepo workspace root. Defaults to Get-DatrixWorkspaceRoot.

 .EXAMPLE
 $directories = Get-DatrixDirectories
 #>
 [CmdletBinding()]
 param(
 [Parameter(Mandatory=$false)]
 [string]$WorkspaceRoot
 )

 if (-not $WorkspaceRoot) {
 $WorkspaceRoot = Get-DatrixWorkspaceRoot
 }

 if (-not (Test-Path $WorkspaceRoot)) {
 return @()
 }

 $directories = @()

 # The showcase repo anchors the workspace; keep it first for stable, readable script output.
 if (Test-Path (Join-Path $WorkspaceRoot "datrix")) {
 $directories += "datrix"
 }

 Get-ChildItem -Path $WorkspaceRoot -Directory |
 Where-Object { $_.Name -like "datrix-*" } |
 Sort-Object Name |
 ForEach-Object { $directories += $_.Name }

 return $directories
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
