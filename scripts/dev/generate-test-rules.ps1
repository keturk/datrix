#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generate @test-rule conformance annotations for test functions using a local LLM.

.DESCRIPTION
    The behaviour is datrix_scripts.dev.generate_test_rules. Walks each package's tests/ tree,
    finds un-annotated test functions, and asks a local model whether each test encodes a
    cross-target conformance rule. In the default (propose) mode it writes reviewable proposals
    under .test-output/test-rules/<package>.json (+ a .md preview) and touches no source. Re-run
    with -Apply to insert the reviewed @test-rule markers above the test functions.

    The markers feed the logic-map Rule Matrix (code-index.ps1 -Canonical / logic-map-report.ps1).
    Runs are resumable: already-annotated functions and already-proposed functions are
    skipped, so you can build the map incrementally.

    With no package, no -All and no -Path it prints its usage and exits 1.

.PARAMETER Projects
    One or more package names (e.g. datrix-codegen-python). Positional.

.PARAMETER All
    Scan every datrix* package's tests tree.

.PARAMETER Apply
    Insert reviewed proposals into the test files (default: propose only).

.PARAMETER Review
    Print a triage report of existing proposals (no LLM, no source changes).

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

.PARAMETER Path
    Restrict to test files under this file or directory (repeatable). The packages are derived
    from the paths when none are named.

.PARAMETER NoSeed
    Do not seed the topic vocabulary from existing markers.

.PARAMETER NoConsolidate
    Skip the topic-consolidation pass.

.PARAMETER IncludeE2e
    Include tests/e2e (excluded by default).

.PARAMETER IncludeIntegration
    Include tests/integration (excluded by default).

.PARAMETER Dbg
    Enable debug logging.

.PARAMETER SelfTest
    Run only the module's self-test: test functions are discovered, a run naming nothing to scan
    prints the usage, and the wrapper seam holds.

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
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true, ParameterSetName = "Run")][string[]]$Projects,
 [Parameter(ParameterSetName = "Run")][switch]$All,
 [Parameter(ParameterSetName = "Run")][switch]$Apply,
 [Parameter(ParameterSetName = "Run")][switch]$Review,
 [Parameter(ParameterSetName = "Run")][ValidateNotNullOrEmpty()][string]$Model,
 [Parameter(ParameterSetName = "Run")][string[]]$LocalMachines,
 [Parameter(ParameterSetName = "Run")][int]$Parallel,
 [Parameter(ParameterSetName = "Run")][int]$Limit,
 [Parameter(ParameterSetName = "Run")][string[]]$Path,
 [Parameter(ParameterSetName = "Run")][switch]$NoSeed,
 [Parameter(ParameterSetName = "Run")][switch]$NoConsolidate,
 [Parameter(ParameterSetName = "Run")][switch]$IncludeE2e,
 [Parameter(ParameterSetName = "Run")][switch]$IncludeIntegration,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.generate_test_rules" -Parameters $PSBoundParameters
exit $LASTEXITCODE
