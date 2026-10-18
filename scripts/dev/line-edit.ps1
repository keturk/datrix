#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Set up the line-edit MCP server (datrix-edit) that agents read and edit files through by line.

.DESCRIPTION
    The datrix-edit server (dev/lib/line_edit_mcp.py, logic in common/lib/datrix_scripts/line_edits.py)
    gives agents read_lines, which shows every line numbered and hashed, and edit_lines, which replaces
    or inserts line ranges -- many at once, across files -- naming the old lines by number and hash
    instead of re-sending their text. Every edit_lines call is judged by the Write/Edit guards through
    the route-line-edits.py hook. Only existing UTF-8 text files under the workspace are read or written.

    Exit codes:
      0 = done
      1 = the request could not be carried out (the message says why)

.PARAMETER Setup
    Set this machine up: write the datrix-edit MCP server into <workspace>\.mcp.json with this
    machine's paths (other servers in the file are kept), approve it for this machine in
    .claude\settings.local.json (gitignored), and remove any older local-scope registration that
    would shadow it. Run once on each development machine, then restart Claude Code. Safe to re-run.

.EXAMPLE
    .\line-edit.ps1 -Setup
#>

[CmdletBinding()]
param(
    [Parameter()] [switch]$Setup
)

$ErrorActionPreference = "Stop"

$McpServerName = "datrix-edit"

if (-not $Setup) {
    Write-Host "Pass -Setup to register the datrix-edit MCP server on this machine (Get-Help .\line-edit.ps1 -Full)." -ForegroundColor Red
    exit 1
}

# Registration writes the MCP server's interpreter, script and PYTHONPATH into .mcp.json; it runs no Python itself.
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1")
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixScriptCommon.psm1") -Force
. (Join-Path $PSScriptRoot "..\common\venv.ps1")
$workspace = Get-DatrixWorkspaceRoot
Install-DatrixProjectMcpServer -Name $McpServerName -PythonExe (Join-Path (Get-DatrixVenvPath) "Scripts\python.exe") `
    -ServerScript (Join-Path $PSScriptRoot "lib\line_edit_mcp.py") -PythonPath (Get-DatrixScriptsPythonPath) `
    -Workspace $workspace -SetupCommand "line-edit.ps1 -Setup"
exit 0
