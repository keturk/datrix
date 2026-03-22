<#
.SYNOPSIS
 Shared helpers for Datrix PowerShell scripts (workspace-relative paths, project lists, input normalization).

.DESCRIPTION
 Imports DatrixPaths.psm1 automatically. Does not load venv.ps1; dot-source venv.ps1 in the caller when needed.

 Project list semantics (see datrix/scripts/README.md):
 - Get-DatrixPackageNamesGlob: metrics -All; filesystem directories under the workspace matching datrix-*.
 - Get-DatrixTestablePackageNames: test runner; canonical repos (DatrixPaths) that exist and contain a tests/ folder.
 - Get-DatrixMonoProjectNames: full-monorepo scans (e.g. duplicate -Mono); canonical repo names in order where the directory exists.
#>

$pathsModule = Join-Path $PSScriptRoot "DatrixPaths.psm1"
Import-Module $pathsModule -Force

function Get-DatrixWorkspaceRootFromScript {
 <#
 .SYNOPSIS
 Resolves the monorepo workspace root from the invoking script path.

 .PARAMETER ScriptPath
 Path to the running .ps1 file (use $MyInvocation.MyCommand.Path).
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $true)]
  [string]$ScriptPath
 )

 return Get-DatrixWorkspaceRoot -ScriptPath $ScriptPath
}

function Normalize-DatrixProjectInput {
 <#
 .SYNOPSIS
 Normalizes a project argument: folder path or bare package name to a directory name.

 .PARAMETER ProjectInput
 User-supplied project name or path.
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $true)]
  [string]$ProjectInput
 )

 $trimmedInput = $ProjectInput.Trim()
 $isPath = $trimmedInput -match '^\.|^\.\\|^[A-Za-z]:\\'
 if ($isPath) {
  try {
   $resolvedPath = Resolve-Path -Path $trimmedInput -ErrorAction Stop
   return Split-Path -Leaf $resolvedPath.Path
  } catch {
   $cleaned = $trimmedInput -replace '[\\/]+$', ''
   return Split-Path -Leaf $cleaned
  }
 }
 return $trimmedInput
}

function Get-DatrixPackageNamesGlob {
 <#
 .SYNOPSIS
 Lists datrix-* directory names under the workspace (metrics -All behavior).

 .PARAMETER WorkspaceRoot
 Monorepo workspace root. Defaults to Get-DatrixWorkspaceRoot.
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $false)]
  [string]$WorkspaceRoot
 )

 if (-not $WorkspaceRoot) {
  $WorkspaceRoot = Get-DatrixWorkspaceRoot
 }

 $projects = @()
 if (Test-Path $WorkspaceRoot) {
  Get-ChildItem -Path $WorkspaceRoot -Directory | Where-Object { $_.Name -like "datrix-*" } | ForEach-Object {
   $projects += $_.Name
  }
 }
 return $projects | Sort-Object
}

function Get-DatrixPackageNamesGlobWithPyProject {
 <#
 .SYNOPSIS
 Lists datrix-* directories under the workspace that contain a pyproject.toml (dependency.ps1 help / discovery).

 .PARAMETER WorkspaceRoot
 Monorepo workspace root. Defaults to Get-DatrixWorkspaceRoot.
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $false)]
  [string]$WorkspaceRoot
 )

 if (-not $WorkspaceRoot) {
  $WorkspaceRoot = Get-DatrixWorkspaceRoot
 }

 $projects = @()
 if (Test-Path $WorkspaceRoot) {
  Get-ChildItem -Path $WorkspaceRoot -Directory | Where-Object { $_.Name -like "datrix-*" } | ForEach-Object {
   $pyproject = Join-Path $_.FullName "pyproject.toml"
   if (Test-Path $pyproject) {
    $projects += $_.Name
   }
  }
 }
 return $projects | Sort-Object
}

function Get-DatrixTestablePackageNames {
 <#
 .SYNOPSIS
 Lists canonical package names that exist under the workspace and contain a tests/ directory (test.ps1 -All behavior).

 .PARAMETER WorkspaceRoot
 Monorepo workspace root. Defaults to Get-DatrixWorkspaceRoot.
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $false)]
  [string]$WorkspaceRoot
 )

 if (-not $WorkspaceRoot) {
  $WorkspaceRoot = Get-DatrixWorkspaceRoot
 }

 $projects = @()
 foreach ($dirPath in (Get-DatrixDirectoryPaths -WorkspaceRoot $WorkspaceRoot)) {
  if (Test-Path (Join-Path $dirPath "tests")) {
   $projects += (Split-Path -Leaf $dirPath)
  }
 }
 return $projects | Sort-Object
}

function Get-DatrixMonoProjectNames {
 <#
 .SYNOPSIS
 Ordered list of canonical monorepo package directory names (DatrixPaths) that exist on disk (e.g. duplicate.ps1 -Mono).

 .PARAMETER WorkspaceRoot
 Monorepo workspace root. Defaults to Get-DatrixWorkspaceRoot.
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $false)]
  [string]$WorkspaceRoot
 )

 if (-not $WorkspaceRoot) {
  $WorkspaceRoot = Get-DatrixWorkspaceRoot
 }

 $names = @()
 foreach ($dir in Get-DatrixDirectories) {
  $p = Join-Path $WorkspaceRoot $dir
  if (Test-Path $p) {
   $names += $dir
  }
 }
 return $names
}

Export-ModuleMember -Function @(
 "Get-DatrixWorkspaceRootFromScript",
 "Normalize-DatrixProjectInput",
 "Get-DatrixPackageNamesGlob",
 "Get-DatrixPackageNamesGlobWithPyProject",
 "Get-DatrixTestablePackageNames",
 "Get-DatrixMonoProjectNames"
)
