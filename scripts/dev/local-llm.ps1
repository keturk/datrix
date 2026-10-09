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
    Show which model servers answer right now, what each holds in memory, and the last -Days of
    usage (default 1).

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
#>

[CmdletBinding()]
param(
    [Parameter()] [switch]$Setup,
    [Parameter()] [switch]$Status,
    [Parameter()] [switch]$Usage,
    [Parameter()] [int]$Days = -1
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$cliScript = Join-Path $scriptDir "lib\local_llm_cli.py"
$mcpScript = Join-Path $scriptDir "lib\local_llm_mcp.py"
$commonDir = Join-Path $scriptsDir "common"
. (Join-Path $commonDir "venv.ps1")
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force

$McpServerName = "datrix-local-llm"

$actions = @(@(
    @{ Name = "-Setup"; Set = [bool]$Setup },
    @{ Name = "-Status"; Set = [bool]$Status },
    @{ Name = "-Usage"; Set = [bool]$Usage }
) | Where-Object { $_.Set })
if ($actions.Count -ne 1) {
    $given = if ($actions.Count) { ($actions | ForEach-Object { $_.Name }) -join ", " } else { "none" }
    Write-Host ("Pass exactly one action: -Setup, -Status or -Usage (given: $given). " +
        "Get-Help .\local-llm.ps1 -Full lists them.") -ForegroundColor Red
    exit 1
}
if ($Days -ge 0 -and $Setup) {
    Write-Host "-Days applies to -Status and -Usage only; -Setup takes no other parameter." -ForegroundColor Red
    exit 1
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

trap {
    Write-Host ""
    Write-Warning "Interrupted by user (Ctrl-C)"
    Invoke-Cleanup
    exit 130
}

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }
    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $venvPath "bin\python"
    }

    if ($Setup) {
        Install-DatrixProjectMcpServer -Name $McpServerName -PythonExe $pythonExe -ServerScript $mcpScript `
            -PythonPath (Get-DatrixScriptsPythonPath) -Workspace (Split-Path -Parent (Split-Path -Parent $scriptsDir)) -SetupCommand "local-llm.ps1 -Setup"
        exit 0
    }

    # @(...) around the whole expression: an if-expression unwraps a one-element array to a string,
    # and splatting a string passes it one character per argument.
    $pyArgs = @(if ($Status) { "status" } else { "usage" })
    if ($Days -ge 0) { $pyArgs += @("--days", $Days) }
    & $pythonExe $cliScript @pyArgs
    exit $LASTEXITCODE
}
catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 1
}
finally {
    Invoke-Cleanup
}
