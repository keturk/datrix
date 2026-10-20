#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Report where subagents spend their context, from Claude Code transcripts.

.DESCRIPTION
 Runs datrix_scripts.metrics.agent_spend. Reads the subagent transcripts of this workspace's Claude
 Code project folder (~\.claude\projects\<workspace slug>\<session>\subagents\agent-*.jsonl,
 labelled by the meta.json beside each) and reports: tool calls and tool-result size by tool;
 Read results by kind of file (task file, design doc, rules, tests, source) and how much was
 whole-file; the files read whole most often and by how many agents; how much source/test
 reading went to files the agent never edited; and one line per agent.

 This measures the spend rules (execution-contract-spend.md §10-§11) instead of guessing.
 Token figures are estimates (characters / 4).

 Exit codes: 0 = report printed, 1 = no transcript matched, 2 = bad argument or no project folder.

.PARAMETER Session
 Only these sessions' subagents (session ids). A value may also be a comma-separated list.

.PARAMETER Days
 Without -Session: subagents whose transcript changed in the last N days (1-3650). Default: 7.

.PARAMETER Transcript
 Explicit transcript paths instead of discovery. A value may also be a comma-separated list.

.PARAMETER Top
 Rows in the per-tool and per-file tables (1-1000). Default: 20.

.PARAMETER SelfTest
 Run only the module's self-test (a planted transcript, no real project folder) and exit.

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
    [int]$Top = 20,
    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.metrics.agent_spend" -Parameters $PSBoundParameters
exit $LASTEXITCODE
