#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Query the code index: definitions, references, outlines, search, logic-map markers.

.DESCRIPTION
    The behaviour is datrix_scripts.dev.code_index. The code index covers every Python, Markdown,
    PowerShell, .dtrx, .dcfg and TypeScript file git sees in the workspace repositories (references
    and logic-map markers are read from Python only) and lives beside the checkout it describes
    (<workspace>\.code-index\). Each development machine builds its own from its own working tree;
    nothing is shared or synchronised between machines, and the first query on a machine builds it
    (about ten seconds). Every query refreshes it first, parsing only files whose content changed,
    and never contacts another machine.

    The index also owns the logic map: each refresh rewrites .logic-map\markers.db whenever the
    @canonical/@pattern/@boundary/@invariant/@test-rule markers in source changed.

    Creating and updating: run -Setup once on each development machine (it builds the index and
    registers the MCP server). After that there is nothing to schedule: every query, from this script
    or from an agent's MCP tool call, first updates the index to the machine's current working tree
    (about 0.2 seconds when little changed), so edits, pulls and branch switches are picked up by the
    next query. The optional module summaries (-Summarize) are cached per machine by content hash.

    Pass exactly one action: -Symbol, -References, -Outline, -Search, -Canonical, -Status, -Refresh,
    -Usage, -Summarize or -Setup.

    Exit codes:
      0 = answered
      1 = the query or the index could not be answered as asked (the message says what to pass)
      2 = -Summarize found no local model server that could answer

.PARAMETER Symbol
    Find definitions of a bare name, a glob (*Resolver), Class.method, or a dotted path.

.PARAMETER Kind
    With -Symbol: only this kind. Python: class, function, method, variable, attribute. Markdown:
    section. PowerShell: function, parameter. TypeScript adds interface, type, enum, namespace.
    .dcfg: config, block, profile, template, key, setting. .dtrx: the language server's outline
    kinds (service, entity, field, endpoint, ...). An unknown kind is refused with the full list.

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
    default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
    With -Summarize: models to use, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
    With -Summarize: request timeout in seconds. Default: 300.

.PARAMETER Setup
    Set this machine up: build (or bring up to date) its index, then write the index's MCP server
    (python -m datrix_scripts.dev.code_index_mcp in the shared venv) into <workspace>\.mcp.json with
    this machine's paths (other servers in the file are kept), and remove any older local-scope
    registration that would shadow it. Claude Code reads .mcp.json for every installation and
    drive-letter spelling. The server is approved for this machine in .claude\settings.local.json
    (gitignored), because Claude Code ignores an approval in the checked-in settings.json. Run once
    on each development machine, then restart Claude Code. Safe to re-run.

.PARAMETER SelfTest
    Run only the module's self-test: exactly one action is required, each query keeps its limit,
    and the wrapper seam holds.

.EXAMPLE
    .\code-index.ps1 -Symbol to_snake_case

.EXAMPLE
    .\code-index.ps1 -References datrix_common.utils.identifier_case.to_snake_case

.EXAMPLE
    .\code-index.ps1 -Outline datrix-common/src/datrix_common/utils/text.py

.EXAMPLE
    .\code-index.ps1 -Canonical text/to-snake

.EXAMPLE
    .\code-index.ps1 -Summarize -Limit 100
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run")][string]$Symbol,
 [Parameter(ParameterSetName = "Run")][string]$Kind,
 [Parameter(ParameterSetName = "Run")][string]$References,
 [Parameter(ParameterSetName = "Run")][string]$Outline,
 [Parameter(ParameterSetName = "Run")][string]$Search,
 [Parameter(ParameterSetName = "Run")][string]$Canonical,
 [Parameter(ParameterSetName = "Run")][switch]$IncludeTestRules,
 [Parameter(ParameterSetName = "Run")][switch]$Status,
 [Parameter(ParameterSetName = "Run")][switch]$Refresh,
 [Parameter(ParameterSetName = "Run")][switch]$Usage,
 [Parameter(ParameterSetName = "Run")][int]$Days = 7,
 [Parameter(ParameterSetName = "Run")][switch]$Summarize,
 [Parameter(ParameterSetName = "Run")][int]$Workers = 4,
 [Parameter(ParameterSetName = "Run")][int]$Limit = -1,
 [Parameter(ParameterSetName = "Run")][string[]]$LocalMachines,
 [Parameter(ParameterSetName = "Run")][string[]]$LlmModel,
 [Parameter(ParameterSetName = "Run")][int]$LlmTimeout = 300,
 [Parameter(ParameterSetName = "Run")][switch]$Setup,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.code_index" -Parameters $PSBoundParameters
exit $LASTEXITCODE
