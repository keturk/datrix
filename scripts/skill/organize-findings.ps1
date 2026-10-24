#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Sort the findings files lying directly in the findings folder into one level of area subfolders, by file name.

.DESCRIPTION
    The behaviour is datrix_scripts.skill.organize_findings. Only *.md files directly in the folder are
    moved; nothing inside a subfolder is touched and no subfolder is created inside another. A file's content
    is never read. The area comes from the name: the area of a merged name (NNNN-<area>-<slug>.md), else the
    first word of the slug when it names an area or an alias (azure-..., ts-..., gate-...). A name that states
    no area is sent, by name only, to a local model that picks one of the areas (python, typescript, backends,
    clients, language, migration, seed, kernel, docker, aws, azure, component, tests, tooling, docs); a name
    carrying a registered customer term is not sent. A move never overwrites an existing file.

    finding-select, finding-close and the skills' inbox scans read *.md directly in one folder: point them
    at an area subfolder with -Dir (implement-finding.ps1 -Dir "<folder>\azure").

    Exit codes: 0 every file is sorted; 1 the folder cannot be read or a move failed; 2 some files stayed
    where they were (a withheld name, or no valid model answer for them); 3 a model was needed and none
    answered.

.PARAMETER Dir
    The findings folder. Default: <workspace>\reports\finding.

.PARAMETER DryRun
    Print the moves; make none.

.PARAMETER NoModel
    Never ask a local model: a name that states no area stays where it is.

.PARAMETER LocalMachines
    Machines (host name or IP) whose Ollama server is searched, in preference order.

.PARAMETER LlmModel
    Use only these models, best first. Default: any model already in memory.

.PARAMETER LlmTimeout
    Timeout in seconds for each request to a ready model. Default: 300.

.PARAMETER SelfTest
    Run only the module's self-test (names, plans, moves, the model path over a loopback server) and the
    wrapper seam checks.

.EXAMPLE
    .\organize-findings.ps1 -DryRun

.EXAMPLE
    .\organize-findings.ps1 -NoModel
#>
[CmdletBinding()]
param(
    [string]$Dir,
    [switch]$DryRun,
    [switch]$NoModel,
    [string[]]$LocalMachines,
    [string[]]$LlmModel,
    [int]$LlmTimeout,
    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.skill.organize_findings" -Parameters $PSBoundParameters
exit $LASTEXITCODE
