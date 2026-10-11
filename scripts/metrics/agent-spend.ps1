#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Report where subagents spend their context, from Claude Code transcripts.

.DESCRIPTION
 Wraps metrics\lib\agent_spend.py. Reads the subagent transcripts of this workspace's Claude
 Code project folder (~\.claude\projects\<workspace slug>\<session>\subagents\agent-*.jsonl,
 labelled by the meta.json beside each) and reports: tool calls and tool-result size by tool;
 Read results by kind of file (task file, design doc, rules, tests, source) and how much was
 whole-file; the files read whole most often and by how many agents; how much source/test
 reading went to files the agent never edited; and one line per agent.

 This measures the spend rules (execution-contract-spend.md §10-§11) instead of guessing.
 Token figures are estimates (characters / 4).

 Exit codes: 0 = report printed, 1 = no transcript matched, 2 = bad argument or no project folder.

.PARAMETER Session
 Only these sessions' subagents (session ids).

.PARAMETER Days
 Without -Session: subagents whose transcript changed in the last N days. Default: 7.

.PARAMETER Transcript
 Explicit transcript paths instead of discovery.

.PARAMETER Top
 Rows in the per-tool and per-file tables. Default: 20.

.EXAMPLE
 .\metrics\agent-spend.ps1 -Days 2
 Subagents of the last two days.

.EXAMPLE
 .\metrics\agent-spend.ps1 -Session 05f209e5-571e-402f-8cf2-29ffd9e1b06b
 The subagents of one orchestrator run.
#>

[CmdletBinding()]
param(
    [string[]]$Session = @(),
    [ValidateRange(1, 3650)]
    [int]$Days = 7,
    [string[]]$Transcript = @(),
    [ValidateRange(1, 1000)]
    [int]$Top = 20
)

$ErrorActionPreference = "Stop"

# `powershell -File` passes "a,b" as one string; accept both that and a real array.
$Session = @($Session | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
$Transcript = @($Transcript | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ })

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$pythonScript = Join-Path $scriptDir "lib\agent_spend.py"
if (-not (Test-Path $pythonScript)) {
    Write-Error "agent_spend.py not found at: $pythonScript"
    exit 2
}

function Invoke-Cleanup { Disable-DatrixVenv }
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

try {
    if (-not (Ensure-DatrixVenv)) {
        Write-Error "Failed to activate the Datrix virtual environment"
        exit 2
    }

    $pythonArgs = @($pythonScript, "--days", $Days, "--top", $Top)
    foreach ($item in $Session) { $pythonArgs += "--session"; $pythonArgs += $item }
    foreach ($item in $Transcript) { $pythonArgs += "--transcript"; $pythonArgs += $item }

    & python @pythonArgs
    exit $LASTEXITCODE
} catch {
    Write-Host "Error: $($_.Exception.Message)" -ForegroundColor Red
    exit 2
} finally {
    Invoke-Cleanup
}
