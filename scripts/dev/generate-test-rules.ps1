#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generate @test-rule conformance annotations for test functions using a local LLM.

.DESCRIPTION
    Walks each package's tests/ tree, finds un-annotated test functions, and asks a
    local model whether each test encodes a cross-target conformance rule. In the
    default (propose) mode it writes reviewable proposals under
    .test-output/test-rules/<package>.json (+ a .md preview) and touches no source. Re-run
    with -Apply to insert the reviewed @test-rule markers above the test functions.

    The markers feed the logic-map Rule Matrix (code-index.ps1 -Canonical / logic-map-report.ps1).
    Runs are resumable: already-annotated functions and already-proposed functions are
    skipped, so you can build the map incrementally.

    Runs lib\generate_test_rules.py in the shared venv.

.PARAMETER Projects
    One or more package names (e.g. datrix-codegen-python). Positional.

.PARAMETER All
    Scan every datrix* package's tests tree.

.PARAMETER Apply
    Insert reviewed proposals into the test files (default: propose only).

.PARAMETER Model
    Model to annotate with (default: exaone-deep:32b). Any searched machine serving it is
    used; it also names the proposal set -Apply and -Review read.

.PARAMETER LocalMachines
    Machines to search for a server running -Model, in preference order. Omit to search
    the default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER Parallel
    Concurrent LLM calls (default: 4).

.PARAMETER Limit
    Max test functions per package this run (0 = no limit). Useful for a sample pass.

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\generate-test-rules.ps1 datrix-codegen-python -Limit 20
    Propose annotations for up to 20 test functions in one package.

.EXAMPLE
    .\generate-test-rules.ps1 -All
    Propose annotations across every package's tests.

.EXAMPLE
    .\generate-test-rules.ps1 datrix-codegen-python -Apply
    Insert the reviewed proposals for one package.
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
    [string[]]$Projects = @(),

    [switch]$All,

    [switch]$Apply,

    [switch]$Review,

    [string]$Model,

    [string[]]$LocalMachines = @(),

    [int]$Parallel,

    [int]$Limit,

    [string[]]$Path,

    [switch]$NoSeed,

    [switch]$NoConsolidate,

    [switch]$IncludeE2e,

    [switch]$IncludeIntegration,

    [switch]$Dbg
)

if ($Projects.Count -eq 0 -and -not $All -and -not $Path) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\generate-test-rules.ps1 -All [-Apply] [-Model <name>] [-NoSeed] [-Parallel <n>] [-Limit <n>] [-Dbg]" -ForegroundColor White
    Write-Host "  .\generate-test-rules.ps1 <project> [project2 ...] [-Apply] [-NoSeed] [-Limit <n>] [-Dbg]" -ForegroundColor White
    Write-Host "  .\generate-test-rules.ps1 -Path <file-or-dir> [-NoSeed] [-Limit <n>] [-Dbg]" -ForegroundColor White
    Write-Host ""
    Write-Host "Use Get-Help .\generate-test-rules.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @(if ($All) { "--all" } else { $Projects })
if ($Apply) { $pyArgs += "--apply" }
if ($Review) { $pyArgs += "--review" }
if ($Model) { $pyArgs += @("--model", $Model) }
foreach ($machine in $LocalMachines) { $pyArgs += @("--local-machine", $machine) }
if ($PSBoundParameters.ContainsKey('Parallel')) { $pyArgs += @("--parallel", "$Parallel") }
if ($PSBoundParameters.ContainsKey('Limit')) { $pyArgs += @("--limit", "$Limit") }
if ($NoSeed) { $pyArgs += "--no-seed" }
foreach ($p in $Path) { $pyArgs += @("--path", $p) }
if ($NoConsolidate) { $pyArgs += "--no-consolidate" }
if ($IncludeE2e) { $pyArgs += "--include-e2e" }
if ($IncludeIntegration) { $pyArgs += "--include-integration" }
if ($Dbg) { $pyArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\generate_test_rules.py") -Arguments $pyArgs)
