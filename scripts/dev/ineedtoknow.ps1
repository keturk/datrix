#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Ask what you need to know: answered from the knowledge base, or gathered by a local model and kept.

.DESCRIPTION
    The behaviour is datrix_scripts.dev.ineedtoknow. Pass exactly one of: a question, -Status,
    -Rebuild or -Prune.

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
    common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
    Models to use, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
    Request timeout in seconds. Default: 120.

.PARAMETER SelfTest
    Run only the module's self-test: exactly one request is required, the question's words are
    joined, and the wrapper seam holds.

.EXAMPLE
    .\ineedtoknow.ps1 -Question "which package owns the gateway route enumeration"

.EXAMPLE
    .\ineedtoknow.ps1 "how does capability_gaps interact with parity gates" -NoLearn

.EXAMPLE
    .\ineedtoknow.ps1 "how is the tenant id validated on service routes" -In "datrix-semantic/src/**/*tenant*.py"

.EXAMPLE
    .\ineedtoknow.ps1 -Status
#>

[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$Question,
 [Parameter(ParameterSetName = "Run")][string[]]$In,
 [Parameter(ParameterSetName = "Run")][switch]$Refresh,
 [Parameter(ParameterSetName = "Run")][switch]$NoLearn,
 [Parameter(ParameterSetName = "Run")][int]$Limit = 0,
 [Parameter(ParameterSetName = "Run")][switch]$Status,
 [Parameter(ParameterSetName = "Run")][switch]$Rebuild,
 [Parameter(ParameterSetName = "Run")][switch]$Prune,
 [Parameter(ParameterSetName = "Run")][string[]]$LocalMachines,
 [Parameter(ParameterSetName = "Run")][string[]]$LlmModel,
 [Parameter(ParameterSetName = "Run")][int]$LlmTimeout = 120,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.ineedtoknow" -Parameters $PSBoundParameters
exit $LASTEXITCODE
