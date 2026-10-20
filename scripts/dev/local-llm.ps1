#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Set up, inspect and measure the local model servers agents read through.

.DESCRIPTION
    The behaviour is datrix_scripts.dev.local_llm. The Ollama servers on the network's machines
    (searched by common/lib/datrix_scripts/local_llm.py) answer for every local-model script, the
    stop-gate judge, and the agents' MCP tools ask_files, digest_log and local_models
    (datrix_scripts.dev.local_llm_mcp). Every request any of them sends is recorded, by size only,
    in <workspace>\.local-llm\usage.jsonl on the machine that sent it.

    Pass exactly one action: -Setup, -Status, -Usage, -Pin or -Unpin.

    Exit codes:
      0 = done
      1 = the request could not be carried out (the message says why)

.PARAMETER Setup
    Set this machine up: write the local-model MCP server (python -m datrix_scripts.dev.local_llm_mcp
    in the shared venv) into <workspace>\.mcp.json with this machine's paths (other servers in the
    file are kept), approve it for this machine in .claude\settings.local.json (gitignored), and
    remove any older local-scope registration that would shadow it. Run once on each development
    machine, then restart Claude Code. Safe to re-run.

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

.PARAMETER SelfTest
    Run only the module's self-test: exactly one action is required, -Days only with -Status or
    -Usage, and the wrapper seam holds.

.EXAMPLE
    .\local-llm.ps1 -Setup

.EXAMPLE
    .\local-llm.ps1 -Status

.EXAMPLE
    .\local-llm.ps1 -Usage -Days 1

.EXAMPLE
    .\local-llm.ps1 -Pin
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run")][switch]$Setup,
 [Parameter(ParameterSetName = "Run")][switch]$Status,
 [Parameter(ParameterSetName = "Run")][switch]$Usage,
 [Parameter(ParameterSetName = "Run")][switch]$Pin,
 [Parameter(ParameterSetName = "Run")][switch]$Unpin,
 [Parameter(ParameterSetName = "Run")][int]$Days = -1,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.local_llm" -Parameters $PSBoundParameters
exit $LASTEXITCODE
