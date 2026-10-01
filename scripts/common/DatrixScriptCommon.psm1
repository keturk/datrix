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
 identity). Never hardcodes a language name.

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

function Get-DatrixLocalLlmArguments {
 <#
 .SYNOPSIS
 Build the shared local-model flags (library/shared/local_llm.py) for a Python script.

 .DESCRIPTION
 Every script that asks a local model for text searches the same machines through
 shared/local_llm.py. The default machine list and the model preference live only there;
 they are overridden only when -LocalMachines / -LlmModel carry values.

 .PARAMETER LocalMachines
 Machines (host name or IP address) to search, in preference order. Empty = the default list.

 .PARAMETER LlmModel
 Models to use, best first. Empty = any model already in memory, else the default load.

 .PARAMETER LlmTimeoutSeconds
 Timeout for each request to a ready model.
 #>
 [CmdletBinding()]
 param(
  [string[]]$LocalMachines = @(),
  [string[]]$LlmModel = @(),
  [Parameter(Mandatory = $true)]
  [int]$LlmTimeoutSeconds
 )

 $llmArgs = @("--local-timeout-ms", ($LlmTimeoutSeconds * 1000))
 foreach ($machine in $LocalMachines) {
  $llmArgs += @("--local-machine", $machine)
 }
 foreach ($model in $LlmModel) {
  $llmArgs += @("--local-model", $model)
 }
 return ,$llmArgs
}

function Get-DatrixClaudeCodeInstallations {
 <#
 .SYNOPSIS
 Every Claude Code that can start a session on this machine.

 .DESCRIPTION
 The CLI on PATH, and the newest build the VS Code extension bundles. They are separate
 installations with different versions, and they key local scope differently (2.0 by
 'D:\datrix', 2.1 by 'D:/datrix'), so a stale local-scope registration must be looked for
 through each of them.
 #>
 $found = @()
 if (Get-Command claude -ErrorAction SilentlyContinue) {
  $found += "claude"
 }
 $extensions = Join-Path $env:USERPROFILE ".vscode\extensions"
 if (Test-Path $extensions) {
  $newest = Get-ChildItem $extensions -Directory -Filter "anthropic.claude-code-*" |
   Where-Object { $_.Name -match '^anthropic\.claude-code-(\d+\.\d+\.\d+)' } |
   Sort-Object { [version]($_.Name -replace '^anthropic\.claude-code-(\d+\.\d+\.\d+).*$', '$1') } -Descending |
   Select-Object -First 1
  if ($newest) {
   $bundled = Join-Path $newest.FullName "resources\native-binary\claude.exe"
   if (Test-Path $bundled) { $found += "`"$bundled`"" }
  }
 }
 return $found
}

function Read-DatrixJsonObject([string]$Path, [string]$SetupCommand) {
 # The file's top-level properties as an ordered table; empty when the file does not exist.
 $table = [ordered]@{}
 if (-not (Test-Path $Path)) {
  return $table
 }
 try {
  $existing = Get-Content $Path -Raw | ConvertFrom-Json
 }
 catch {
  throw "$Path is not valid JSON ($($_.Exception.Message)); fix or delete it and re-run $SetupCommand."
 }
 foreach ($property in $existing.PSObject.Properties) {
  $table[$property.Name] = $property.Value
 }
 return $table
}

function Write-DatrixJsonFile([string]$Path, [System.Collections.IDictionary]$Table) {
 $json = $Table | ConvertTo-Json -Depth 20
 [System.IO.File]::WriteAllText($Path, $json + "`n", (New-Object System.Text.UTF8Encoding $false))
}

function Remove-DatrixLocalMcpRegistrations([string]$Name, [string]$Workspace) {
 # Earlier setups registered servers in local scope (~/.claude.json), keyed by the exact
 # working-directory string -- once per Claude Code installation, once per drive-letter
 # spelling. The project .mcp.json replaces all of them; a stale local entry would shadow it.
 # Each 'claude' call runs from cmd with that spelling as its working directory, because
 # PowerShell hands child processes the upper-case drive.
 $spellings = @(
  ($Workspace.Substring(0, 1).ToUpperInvariant() + $Workspace.Substring(1)),
  ($Workspace.Substring(0, 1).ToLowerInvariant() + $Workspace.Substring(1))
 ) | Select-Object -Unique
 # 'claude mcp get' reports an absent server on stderr, which Windows PowerShell turns into a
 # terminating error under "Stop"; exit codes are checked explicitly instead.
 $previousPreference = $ErrorActionPreference
 $ErrorActionPreference = "Continue"
 try {
  foreach ($claude in @(Get-DatrixClaudeCodeInstallations)) {
   foreach ($directory in $spellings) {
    $inDirectory = "cd /d `"$directory`" && $claude mcp"
    cmd /s /c "`"$inDirectory remove --scope local $Name`"" *> $null
    $details = cmd /s /c "`"$inDirectory get $Name`"" 2>&1 | Out-String
    if ($details -match "Scope:\s*Local") {
     throw "A local-scope '$Name' registration ($claude, $directory) could not be removed: $details"
    }
   }
  }
 }
 finally {
  $ErrorActionPreference = $previousPreference
 }
}

function Install-DatrixProjectMcpServer {
 <#
 .SYNOPSIS
 Set up a stdio MCP server for the workspace on this machine: the project .mcp.json, its
 per-machine approval, and the removal of any older local-scope registration.

 .DESCRIPTION
 Writes the server into <workspace>\.mcp.json with this machine's paths. Claude Code reads that
 file from the folder it opens, for every installation and whatever the drive-letter case, so
 one file per machine replaces per-installation registrations. It is written here, not checked
 in, because its paths are this machine's (the venv's Python, this checkout's server). Other
 servers already in the file are kept.

 Claude Code starts a project .mcp.json server only once it is approved on the machine, and
 current builds ignore an approval in the checked-in settings.json -- a repository must not
 approve its own servers -- so the server is named in .claude\settings.local.json
 (gitignored, per machine). Running the setup is the approval. Every other setting already
 in that file is kept.

 Throws when a file is not valid JSON or a stale local registration cannot be removed.

 .PARAMETER Name
 The MCP server name (its tools appear as mcp__<Name>__<tool>).

 .PARAMETER PythonExe
 The interpreter that runs the server.

 .PARAMETER ServerScript
 The server's Python script.

 .PARAMETER Workspace
 The workspace root the sessions start in.

 .PARAMETER SetupCommand
 The command that re-runs this setup, named in the messages.
 #>
 [CmdletBinding()]
 param(
  [Parameter(Mandatory = $true)] [string]$Name,
  [Parameter(Mandatory = $true)] [string]$PythonExe,
  [Parameter(Mandatory = $true)] [string]$ServerScript,
  [Parameter(Mandatory = $true)] [string]$Workspace,
  [Parameter(Mandatory = $true)] [string]$SetupCommand
 )

 $configPath = Join-Path $Workspace ".mcp.json"
 $config = Read-DatrixJsonObject $configPath $SetupCommand
 $servers = [ordered]@{}
 if ($config.Contains("mcpServers") -and $config["mcpServers"]) {
  foreach ($server in $config["mcpServers"].PSObject.Properties) {
   $servers[$server.Name] = $server.Value
  }
 }
 $servers[$Name] = [ordered]@{ type = "stdio"; command = $PythonExe; args = @($ServerScript) }
 $config["mcpServers"] = $servers
 Write-DatrixJsonFile $configPath $config
 Write-Host "Wrote '$Name' into $configPath." -ForegroundColor Green

 $localSettings = Join-Path $Workspace ".claude\settings.local.json"
 $settings = Read-DatrixJsonObject $localSettings $SetupCommand
 $approved = @(if ($settings.Contains("enabledMcpjsonServers")) { $settings["enabledMcpjsonServers"] | Where-Object { $_ } })
 if ($approved -notcontains $Name) {
  $approved += $Name
 }
 $settings["enabledMcpjsonServers"] = $approved
 Write-DatrixJsonFile $localSettings $settings

 Remove-DatrixLocalMcpRegistrations $Name $Workspace
 Write-Host ("Approved '$Name' for this machine in $localSettings. Restart Claude Code (in VS Code: " +
  "Developer: Reload Window) to load its tools.") -ForegroundColor Green
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
 "Get-DatrixInstalledTargets",
 "Get-DatrixLocalLlmArguments",
 "Get-DatrixClaudeCodeInstallations",
 "Install-DatrixProjectMcpServer"
)
