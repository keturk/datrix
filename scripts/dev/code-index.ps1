#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Query the code index: definitions, references, outlines, search, logic-map markers.

.DESCRIPTION
    The code index covers every Python file git sees in the workspace repositories and lives
    beside the checkout it describes (<workspace>\.code-index\). Each development machine builds
    its own from its own working tree; nothing is shared or synchronised between machines, and the
    first query on a machine builds it (about ten seconds). Every query refreshes it first, parsing
    only files whose content changed, and never contacts another machine.

    The index also owns the logic map: each refresh rewrites .logic-map\markers.db whenever the
    @canonical/@pattern/@boundary/@invariant/@test-rule markers in source changed.

    Creating and updating: run -Setup once on each development machine (it builds the index and
    registers the MCP server). After that there is nothing to schedule: every query, from this script
    or from an agent's MCP tool call, first updates the index to the machine's current working tree
    (about 0.2 seconds when little changed), so edits, pulls and branch switches are picked up by the
    next query. The optional module summaries (-Summarize) are cached per machine by content hash.

    Exit codes:
      0 = answered
      1 = the query or the index could not be answered as asked (the message says what to pass)
      2 = -Summarize found no local model server that could answer

.PARAMETER Symbol
    Find definitions of a bare name, a glob (*Resolver), Class.method, or a dotted path.

.PARAMETER Kind
    With -Symbol: only this kind (class, function, method, variable, attribute).

.PARAMETER References
    Find the uses of a definition (a bare name, Class.method, or dotted path), resolved through imports.

.PARAMETER Outline
    List a file's definitions with line ranges and signatures. A workspace-relative path, a unique
    path suffix, or a dotted module name.

.PARAMETER Search
    Ranked full-text search over names, signatures, docstrings, module summaries and markers.

.PARAMETER Canonical
    Look up logic-map markers by topic path, topic segment, or words.

.PARAMETER IncludeTestRules
    With -Canonical: include @test-rule markers.

.PARAMETER Status
    Report what the index holds: files, definitions, markers, summary coverage, syntax errors.

.PARAMETER Refresh
    Bring the index up to date and report what changed.

.PARAMETER Usage
    Report how much agents on this machine used the index, against the greps, whole-file reads of
    large Python files and shell searches it could have answered (logged by the record-search-usage
    hook to <workspace>\.code-index\usage.jsonl).

.PARAMETER Days
    With -Usage: days to cover. Default: 7; 0 = everything logged.

.PARAMETER Summarize
    Ask a local model to summarize modules that have no summary for their current content. Sends
    each module's outline and source to the model server over the local network.

.PARAMETER Workers
    With -Summarize: parallel requests. Default: 4.

.PARAMETER Limit
    Results to show (-Symbol, -Search, -Canonical), files to list (-References), or modules to
    summarize (-Summarize; 0 = all). Default: each query's own default; 200 for -Summarize.

.PARAMETER LocalMachines
    With -Summarize: machines to search for model servers, in preference order. Omit to search the
    default list in library/shared/local_llm.py.

.PARAMETER LlmModel
    With -Summarize: models to use, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
    With -Summarize: request timeout in seconds. Default: 300.

.PARAMETER Setup
    Set this machine up: build (or bring up to date) its index, then write the index's MCP server
    into <workspace>\.mcp.json with this machine's paths (other servers in the file are kept), and
    remove any older local-scope registration that would shadow it. Claude Code reads .mcp.json
    for every installation and drive-letter spelling. The server is approved for this machine in
    .claude\settings.local.json (gitignored), because Claude Code ignores an approval in the
    checked-in settings.json. Run once on each development machine, then restart Claude Code.
    Safe to re-run.

.EXAMPLE
    .\code-index.ps1 -Symbol to_snake_case

.EXAMPLE
    .\code-index.ps1 -References datrix_common.utils.text.to_snake_case

.EXAMPLE
    .\code-index.ps1 -Outline datrix-common/src/datrix_common/utils/text.py

.EXAMPLE
    .\code-index.ps1 -Canonical text/to-snake

.EXAMPLE
    .\code-index.ps1 -Summarize -Limit 100
#>

[CmdletBinding()]
param(
    [Parameter()] [string]$Symbol = "",
    [Parameter()] [ValidateSet("", "class", "function", "method", "variable", "attribute")] [string]$Kind = "",
    [Parameter()] [string]$References = "",
    [Parameter()] [string]$Outline = "",
    [Parameter()] [string]$Search = "",
    [Parameter()] [string]$Canonical = "",
    [Parameter()] [switch]$IncludeTestRules,
    [Parameter()] [switch]$Status,
    [Parameter()] [switch]$Refresh,
    [Parameter()] [switch]$Usage,
    [Parameter()] [int]$Days = 7,
    [Parameter()] [switch]$Summarize,
    [Parameter()] [int]$Workers = 4,
    [Parameter()] [int]$Limit = -1,
    [Parameter()] [string[]]$LocalMachines = @(),
    [Parameter()] [string[]]$LlmModel = @(),
    [Parameter()] [int]$LlmTimeout = 300,
    [Parameter()] [switch]$Setup
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$libraryDir = Join-Path $scriptsDir "library"
$cliScript = Join-Path $libraryDir "dev\code_index_cli.py"
$mcpScript = Join-Path $libraryDir "dev\code_index_mcp.py"
$commonDir = Join-Path $scriptsDir "common"
. (Join-Path $commonDir "venv.ps1")
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force

$McpServerName = "datrix-code-index"

# @(...) around the pipeline: one surviving hashtable would otherwise be the value itself,
# and a hashtable's .Count is its number of keys.
$actions = @(@(
    @{ Name = "-Symbol"; Set = [bool]$Symbol },
    @{ Name = "-References"; Set = [bool]$References },
    @{ Name = "-Outline"; Set = [bool]$Outline },
    @{ Name = "-Search"; Set = [bool]$Search },
    @{ Name = "-Canonical"; Set = [bool]$Canonical },
    @{ Name = "-Status"; Set = [bool]$Status },
    @{ Name = "-Refresh"; Set = [bool]$Refresh },
    @{ Name = "-Usage"; Set = [bool]$Usage },
    @{ Name = "-Summarize"; Set = [bool]$Summarize },
    @{ Name = "-Setup"; Set = [bool]$Setup }
) | Where-Object { $_.Set })
if ($actions.Count -ne 1) {
    $given = if ($actions.Count) { ($actions | ForEach-Object { $_.Name }) -join ", " } else { "none" }
    Write-Host ("Pass exactly one action: -Symbol, -References, -Outline, -Search, -Canonical, -Status, " +
        "-Refresh, -Usage, -Summarize or -Setup (given: $given). Get-Help .\code-index.ps1 -Full lists them.") -ForegroundColor Red
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
        & $pythonExe $cliScript refresh
        if ($LASTEXITCODE -ne 0) {
            Write-Host "Building the index failed (see above); the MCP server was not set up." -ForegroundColor Red
            exit $LASTEXITCODE
        }
        Install-DatrixProjectMcpServer -Name $McpServerName -PythonExe $pythonExe -ServerScript $mcpScript `
            -Workspace (Split-Path -Parent (Split-Path -Parent $scriptsDir)) -SetupCommand "code-index.ps1 -Setup"
        exit 0
    }

    $pyArgs = @()
    if ($Symbol) {
        $pyArgs += @("symbol", $Symbol)
        if ($Kind) { $pyArgs += @("--kind", $Kind) }
    }
    elseif ($References) { $pyArgs += @("refs", $References) }
    elseif ($Outline) { $pyArgs += @("outline", $Outline) }
    elseif ($Search) { $pyArgs += @("search", $Search) }
    elseif ($Canonical) {
        $pyArgs += @("canonical", $Canonical)
        if ($IncludeTestRules) { $pyArgs += "--test-rules" }
    }
    elseif ($Status) { $pyArgs += "status" }
    elseif ($Refresh) { $pyArgs += "refresh" }
    elseif ($Usage) { $pyArgs += @("usage", "--days", $Days) }
    elseif ($Summarize) {
        $pyArgs += @("summarize", "--workers", $Workers)
        $pyArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
    }
    if ($Limit -ge 0 -and -not ($Outline -or $Status -or $Refresh -or $Usage)) {
        $pyArgs += @("--limit", $Limit)
    }

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
