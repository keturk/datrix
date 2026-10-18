#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Set up, inspect and measure the local model servers agents read through.

.DESCRIPTION
    The Ollama servers on the network's machines (searched by
    common/lib/datrix_scripts/local_llm.py) answer for every local-model script, the stop-gate
    judge, and the agents' MCP tools ask_files, digest_log and local_models (dev/lib/local_llm_mcp.py).
    Every request any of them sends is recorded, by size only, in
    <workspace>\.local-llm\usage.jsonl on the machine that sent it.

    Exit codes:
      0 = done
      1 = the request could not be carried out (the message says why)

.PARAMETER Setup
    Set this machine up: write the local-model MCP server into <workspace>\.mcp.json with this
    machine's paths (other servers in the file are kept), approve it for this machine in
    .claude\settings.local.json (gitignored), and remove any older local-scope registration that
    would shadow it. Run once on each development machine, then restart Claude Code. Safe to
    re-run.

.PARAMETER Status
    Show which model servers answer right now, what each holds in memory, a line for each machine
    holding no model indefinitely (see -Pin), and the last -Days of usage (default 1).

.PARAMETER Pin
    On each reachable machine, load the first model of the load preference it has installed
    (qwen3-coder:30b-ctx32k, then qwen3.6:35b) and keep it resident indefinitely, so the hooks and
    tools that use only resident models (the red-run digest answers within seconds) find one.
    Prints per machine what was pinned, or why nothing was. Later requests never shorten the pin.

.PARAMETER Unpin
    On each reachable machine, unload every model held resident indefinitely, freeing its GPU
    memory. Prints per machine what was released.

.PARAMETER Usage
    Report local-model requests by caller (script, hook or MCP tool) and by server over the last
    -Days (default 7; 0 = everything logged).

.PARAMETER Days
    With -Status or -Usage: days to cover.

.EXAMPLE
    .\local-llm.ps1 -Setup

.EXAMPLE
    .\local-llm.ps1 -Status

.EXAMPLE
    .\local-llm.ps1 -Usage -Days 1

.EXAMPLE
    .\local-llm.ps1 -Pin
#>

[CmdletBinding()]
param(
    [Parameter()] [switch]$Setup,
    [Parameter()] [switch]$Status,
    [Parameter()] [switch]$Usage,
    [Parameter()] [switch]$Pin,
    [Parameter()] [switch]$Unpin,
    [Parameter()] [int]$Days = -1
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$McpServerName = "datrix-local-llm"

$actions = @(@(
    @{ Name = "-Setup"; Set = [bool]$Setup },
    @{ Name = "-Status"; Set = [bool]$Status },
    @{ Name = "-Usage"; Set = [bool]$Usage },
    @{ Name = "-Pin"; Set = [bool]$Pin },
    @{ Name = "-Unpin"; Set = [bool]$Unpin }
) | Where-Object { $_.Set })
if ($actions.Count -ne 1) {
    $given = if ($actions.Count) { ($actions | ForEach-Object { $_.Name }) -join ", " } else { "none" }
    Write-Host ("Pass exactly one action: -Setup, -Status, -Usage, -Pin or -Unpin (given: $given). " +
        "Get-Help .\local-llm.ps1 -Full lists them.") -ForegroundColor Red
    exit 1
}
if ($Days -ge 0 -and -not ($Status -or $Usage)) {
    Write-Host "-Days applies to -Status and -Usage only; $($actions[0].Name) takes no other parameter." -ForegroundColor Red
    exit 1
}

if ($Setup) {
    # Registration writes the MCP server's interpreter, script and PYTHONPATH into .mcp.json; it
    # runs no Python itself.
    Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1")
    Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
    $workspace = Get-DatrixWorkspaceRoot
    Install-DatrixProjectMcpServer -Name $McpServerName -PythonExe (Get-DatrixVenvPython) `
        -ServerScript (Join-Path $PSScriptRoot "lib\local_llm_mcp.py") -PythonPath (Get-DatrixScriptsPythonPath) `
        -Workspace $workspace -SetupCommand "local-llm.ps1 -Setup"
    exit 0
}

# @(...) around the whole expression: an if-expression unwraps a one-element array to a string,
# and splatting a string passes it one character per argument.
$pythonArgs = @(if ($Status) { "status" } elseif ($Pin) { "pin" } elseif ($Unpin) { "unpin" } else { "usage" })
if ($Days -ge 0) { $pythonArgs += @("--days", $Days) }
exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\local_llm_cli.py") -Arguments $pythonArgs)
