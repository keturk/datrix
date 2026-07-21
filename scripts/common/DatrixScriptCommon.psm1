<#
.SYNOPSIS
 Shared helpers for Datrix PowerShell scripts (workspace-relative paths, project lists, input normalization).

.DESCRIPTION
 Imports DatrixPaths.psm1 automatically. Does not load venv.ps1; dot-source venv.ps1 in the caller when needed.

 Project list semantics (see datrix/scripts/README.md):
 - Get-DatrixPackageNamesGlob: metrics -All; filesystem directories under the workspace matching datrix-*.
 - Get-DatrixTestablePackageNames: test runner; workspace datrix-* dirs with a tests/ folder (excludes retired and the test-free datrix showcase repo); matches status_tests.py discovery.
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

function ConvertTo-DatrixProjectName {
 <#
 .SYNOPSIS
 Converts a project argument (folder path or bare package name) to a directory name.

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
 Lists datrix package directory names under the workspace that contain a tests/ directory (test.ps1 -All behavior).

 .DESCRIPTION
 Discovers packages by scanning the workspace root (same idea as status_tests.py get_datrix_projects), not only
 the hardcoded Get-DatrixDirectories list, so packages like datrix-codegen-common are included.

 Matches "datrix-*" toolchain packages only. The "datrix" showcase repo is NOT a testable
 package — it holds docs, examples, and scripts and hosts no test suite by design — so it is
 never matched here even if a stray tests/ directory appears.

 Retired names merged into datrix-common are excluded: datrix-core, datrix-codegen.

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

 $retired = @("datrix-core", "datrix-codegen")
 $projects = @()
 if (Test-Path $WorkspaceRoot) {
  Get-ChildItem -Path $WorkspaceRoot -Directory |
   Where-Object {
    $_.Name -like "datrix-*" -and
    $retired -notcontains $_.Name -and
    (Test-Path (Join-Path $_.FullName "tests"))
   } |
   ForEach-Object { $projects += $_.Name }
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

function Get-DatrixInstalledPlatforms {
 <#
 .SYNOPSIS
 Return the names of all installed `datrix.platforms` entry-point plugins in the given Python environment.

 .DESCRIPTION
 Enumerates the `datrix.platforms` entry-point group at runtime (importlib.metadata) so the
 installed platform set is discovered, never hardcoded. Installing a datrix-codegen-<provider>
 package makes its platform name appear here with no script edit (DI-6 / D4 open
 identity). Never hardcodes aws/azure/docker.

 Fails loud (throws) on a non-zero exit from the python invocation — a query failure must be
 distinguishable from the real, different state "zero platforms installed".

 .PARAMETER PythonExe
 Path to the python.exe to query. Caller resolves this via Get-DatrixVenvPath (venv.ps1).
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $true)]
  [string]$PythonExe
 )

 # Single-quoted here-string + single-quoted python literals + per-line print:
 # embedding double-quotes in a `python -c` argument gets mangled by Windows
 # PowerShell's native-command quoting, so this script deliberately uses no
 # double-quotes.
 $pyScript = @'
import importlib.metadata as m
for name in sorted(e.name for e in m.entry_points(group='datrix.platforms')):
    print(name)
'@
 $output = & $PythonExe -c $pyScript
 if ($LASTEXITCODE -ne 0) {
  throw "Failed to enumerate installed datrix.platforms plugins via $PythonExe (exit $LASTEXITCODE)."
 }
 return @($output | Where-Object { $_.Trim() -ne "" })
}

Export-ModuleMember -Function @(
 "Get-DatrixWorkspaceRootFromScript",
 "ConvertTo-DatrixProjectName",
 "Get-DatrixPackageNamesGlob",
 "Get-DatrixPackageNamesGlobWithPyProject",
 "Get-DatrixTestablePackageNames",
 "Get-DatrixMonoProjectNames",
 "Get-DatrixInstalledPlatforms"
)
