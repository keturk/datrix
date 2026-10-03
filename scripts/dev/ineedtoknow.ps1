#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Ask what you need to know: answered from the knowledge base, or gathered by a local model and kept.

.DESCRIPTION
    Agents and developers ask a question in their own words instead of loading whole docs. The
    knowledge base answers from the project's own docs (architecture, knowledge packs, agent rules,
    execution contract, script references, package architecture docs), cut into chunks by heading,
    and from answers learned earlier. It gives a brief answer with the file and line range to open.

    When the knowledge base holds no answer, a local model server (if one answers) reads the closest
    chunks of the docs, plus any files named with -In, and writes a short cited answer. The answer is
    kept only when every citation names a file and line the model was shown and every quoted snippet
    is in what it was shown; a failed answer is reported and never stored. A kept answer expires when
    a file it cites changes.

    Storage. The database is per machine, at <workspace>\.knowledge\knowledge.db (override with the
    DATRIX_KNOWLEDGE_DB environment variable). Learned answers are also written as one markdown file
    each to datrix\docs\knowledge\learned\, which is committed: another machine rebuilds or updates
    its database from those files after a pull, importing each one whose cited files still match
    there. Curated chunks need no copy; the docs themselves are the source. Every invocation first
    brings the database up to date with the docs and the learned files.

    Exit codes:
      0 = answered
      1 = the request could not be carried out (the message says why)
      2 = no answer: not in the knowledge base, and no local model could add one

.PARAMETER Question
    What you need to know, in your own words.

.PARAMETER In
    Files to read as well (workspace-relative path or glob; framework repositories only). Implies a
    local-model read instead of a lookup.

.PARAMETER Refresh
    Skip the lookup and have a local model read the closest docs again, replacing a stored answer.

.PARAMETER NoLearn
    Look up only; never contact a local model.

.PARAMETER Limit
    Answers to show. Default: 3.

.PARAMETER Status
    Show what the knowledge base holds and how many learned files are stale on this machine.

.PARAMETER Rebuild
    Drop the database and rebuild it from the docs and the committed learned files.

.PARAMETER Prune
    Delete learned files whose cited files changed on this machine (a git change to commit).

.PARAMETER LocalMachines
    Machines to search for model servers, in preference order. Omit for the default list in
    library/shared/local_llm.py.

.PARAMETER LlmModel
    Models to use, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
    Request timeout in seconds. Default: 120.

.EXAMPLE
    .\ineedtoknow.ps1 -Question "which package owns the gateway route enumeration"

.EXAMPLE
    .\ineedtoknow.ps1 "how does capability_gaps interact with parity gates" -NoLearn

.EXAMPLE
    .\ineedtoknow.ps1 "how is the tenant id validated on service routes" -In "datrix-semantic/src/**/*tenant*.py"

.EXAMPLE
    .\ineedtoknow.ps1 -Status
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)] [string[]]$Question = @(),
    [Parameter()] [string[]]$In = @(),
    [Parameter()] [switch]$Refresh,
    [Parameter()] [switch]$NoLearn,
    [Parameter()] [int]$Limit = 0,
    [Parameter()] [switch]$Status,
    [Parameter()] [switch]$Rebuild,
    [Parameter()] [switch]$Prune,
    [Parameter()] [string[]]$LocalMachines = @(),
    [Parameter()] [string[]]$LlmModel = @(),
    [Parameter()] [int]$LlmTimeout = 120
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsDir = Split-Path -Parent $scriptDir
$libraryDir = Join-Path $scriptsDir "library"
$cliScript = Join-Path $libraryDir "dev\ineedtoknow_cli.py"
$commonDir = Join-Path $scriptsDir "common"
. (Join-Path $commonDir "venv.ps1")
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force

$questionText = ($Question -join " ").Trim()
$actions = @(@(
    @{ Name = "a question"; Set = [bool]$questionText },
    @{ Name = "-Status"; Set = [bool]$Status },
    @{ Name = "-Rebuild"; Set = [bool]$Rebuild },
    @{ Name = "-Prune"; Set = [bool]$Prune }
) | Where-Object { $_.Set })
if ($actions.Count -ne 1) {
    $given = if ($actions.Count) { ($actions | ForEach-Object { $_.Name }) -join ", " } else { "none" }
    Write-Host ("Pass exactly one of: a question, -Status, -Rebuild or -Prune (given: $given). " +
        "Get-Help .\ineedtoknow.ps1 -Full lists them.") -ForegroundColor Red
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

    # @(...) so a single argument stays an array and splats as one argument.
    $pyArgs = @()
    if ($questionText) { $pyArgs += $questionText }
    if ($Status) { $pyArgs += "--status" }
    if ($Rebuild) { $pyArgs += "--rebuild" }
    if ($Prune) { $pyArgs += "--prune" }
    foreach ($spec in $In) { $pyArgs += @("--in", $spec) }
    if ($Refresh) { $pyArgs += "--refresh" }
    if ($NoLearn) { $pyArgs += "--no-learn" }
    if ($Limit -gt 0) { $pyArgs += @("--limit", $Limit) }
    $pyArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout

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
