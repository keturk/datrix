<#
.SYNOPSIS
 Shared helpers for Datrix PowerShell scripts (workspace-relative paths, project lists, input normalization).

.DESCRIPTION
 Imports DatrixPaths.psm1 automatically. Does not load venv.ps1; dot-source venv.ps1 in the caller when needed.

 Project list semantics (see datrix/scripts/README.md):
 - Get-DatrixPackageNamesGlob: metrics -All; filesystem directories under the workspace matching datrix-*.
 - Get-DatrixTestablePackageNames: test runner; workspace datrix-* dirs carrying a suite -- a tests/ folder (pytest) or a package.json with a "test" script (Node) -- excluding retired names and the test-free datrix showcase repo; matches shared/package_suites.py discovery.
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

function Test-DatrixNodeSuite {
 <#
 .SYNOPSIS
 True when a package directory declares a Node test suite (a package.json with a "test" script).

 .DESCRIPTION
 A manifest that cannot be read or parsed is treated as declaring NO suite: guessing
 "testable" would put a package into test.ps1 -All that no runner can execute.

 .PARAMETER PackagePath
 Full path to the package directory.
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $true)]
  [string]$PackagePath
 )

 $manifestPath = Join-Path $PackagePath "package.json"
 if (-not (Test-Path $manifestPath -PathType Leaf)) {
  return $false
 }
 try {
  $manifest = Get-Content -Path $manifestPath -Raw -Encoding utf8 -ErrorAction Stop | ConvertFrom-Json -ErrorAction Stop
 } catch {
  Write-Verbose "Could not parse ${manifestPath}: $_"
  return $false
 }
 if ($null -eq $manifest -or $null -eq $manifest.scripts) {
  return $false
 }
 return ($manifest.scripts.PSObject.Properties.Name -contains "test")
}

function Get-DatrixTestablePackageNames {
 <#
 .SYNOPSIS
 Lists datrix package directory names under the workspace that carry a test suite (test.ps1 -All behavior).

 .DESCRIPTION
 Discovers packages by scanning the workspace root (same idea as status_tests.py get_datrix_projects), not only
 the hardcoded Get-DatrixDirectories list, so packages like datrix-codegen-common are included.

 A package carries a suite when it has EITHER marker below. Datrix is a multi-language
 toolchain and its own tooling has to be one too: datrix-vscode is a TypeScript package
 whose suite runs under Node, and it writes the same .test_results artifacts a pytest
 package does, so every downstream consumer works unchanged.

   tests/ directory                    -> pytest suite
   package.json with a "test" script   -> Node suite

 This predicate is the PowerShell half of one fact; the Python half is
 scripts/library/shared/package_suites.py, and test-tooling-parsing-gate.ps1 compares the
 two sets on every run so they cannot drift apart silently.

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
    (
     (Test-Path (Join-Path $_.FullName "tests")) -or
     (Test-DatrixNodeSuite -PackagePath $_.FullName)
    )
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

 return Get-DatrixInstalledTargets -PythonExe $PythonExe -Group "datrix.platforms"
}

function Get-DatrixInstalledLanguages {
 <#
 .SYNOPSIS
 Return the names of all installed `datrix.languages` entry-point plugins in the given Python environment.

 .DESCRIPTION
 Enumerates the `datrix.languages` entry-point group at runtime (importlib.metadata) so the
 installed language set is discovered, never hardcoded. Installing a datrix-codegen-<lang>
 package makes its language name appear here with no script edit (DI-6 / D4 open
 identity). Never hardcodes python/typescript/dotnet/java.

 Fails loud (throws) on a non-zero exit from the python invocation — a query failure must be
 distinguishable from the real, different state "zero languages installed".

 .PARAMETER PythonExe
 Path to the python.exe to query. Caller resolves this via Get-DatrixVenvPath (venv.ps1).
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $true)]
  [string]$PythonExe
 )

 return Get-DatrixInstalledTargets -PythonExe $PythonExe -Group "datrix.languages"
}

function Get-DatrixInstalledTargets {
 <#
 .SYNOPSIS
 Return the sorted names of every entry-point plugin registered under an entry-point group.

 .DESCRIPTION
 Shared enumerator behind Get-DatrixInstalledLanguages / Get-DatrixInstalledPlatforms. Queries
 importlib.metadata at runtime so the installed target set is discovered, never hardcoded.
 Fails loud (throws) on a non-zero python exit so a query failure is distinguishable from the
 real, different state "zero plugins installed".

 .PARAMETER PythonExe
 Path to the python.exe to query.

 .PARAMETER Group
 Entry-point group name, e.g. "datrix.languages" or "datrix.platforms".
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $true)]
  [string]$PythonExe,
  [Parameter(Mandatory = $true)]
  [string]$Group
 )

 # Single-quoted here-string + single-quoted python literals + per-line print:
 # embedding double-quotes in a `python -c` argument gets mangled by Windows
 # PowerShell's native-command quoting, so this script deliberately uses no
 # double-quotes. The group name is passed via argv (sys.argv[1]) rather than
 # interpolated into the source, keeping the here-string a constant.
 $pyScript = @'
import importlib.metadata as m, sys
for name in sorted(e.name for e in m.entry_points(group=sys.argv[1])):
    print(name)
'@
 $output = & $PythonExe -c $pyScript $Group
 if ($LASTEXITCODE -ne 0) {
  throw "Failed to enumerate installed $Group plugins via $PythonExe (exit $LASTEXITCODE)."
 }
 return @($output | Where-Object { $_.Trim() -ne "" })
}

Export-ModuleMember -Function @(
 "Get-DatrixWorkspaceRootFromScript",
 "ConvertTo-DatrixProjectName",
 "Get-DatrixPackageNamesGlob",
 "Get-DatrixPackageNamesGlobWithPyProject",
 "Test-DatrixNodeSuite",
 "Get-DatrixTestablePackageNames",
 "Get-DatrixMonoProjectNames",
 "Get-DatrixInstalledPlatforms",
 "Get-DatrixInstalledLanguages",
 "Get-DatrixInstalledTargets"
)
