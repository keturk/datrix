#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run the affected set of Datrix package suites concurrently and return one verdict.
.DESCRIPTION
 Runs datrix_scripts.test.affected_gate in gate mode. A HUMAN-ONLY tool: it runs whole package suites, and
 guard-full-suite-runs.py refuses every agent invocation except -SelfTest. Runs the changed packages (-Projects, or
 every package with -All) plus the consumers named with -Consumers; -NoConsumers states that none is reached, and one
 of the two is required unless -All. Every other importer is printed as excluded. Children (test.ps1 <pkg>) run
 longest-first within the logical cores (-MaxConcurrent caps them, -WorkersPerChild fixes each child's xdist
 workers); a package whose green full run's suite-input fingerprint still matches is CARRIED unless -NoCarry.
 -Mypy also type-checks the changed packages; -Force starts over a run that looks in-progress. Writes
 affected-gate.json to <workspace>\.tmp\test\ unless -Output names a path. Exit 0 GREEN, 1 RED, 2 usage error.
 -SelfTest runs only the scheduler's self-test. python -m datrix_scripts.test.affected_gate --help describes every option.
.EXAMPLE
 .\test\affected-gate.ps1 -Projects datrix-codegen-common -Consumers datrix-codegen-python,datrix-cli
#>
[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)][string[]]$Projects,
 [string[]]$Consumers, [switch]$NoConsumers, [switch]$All, [int]$MaxConcurrent, [int]$WorkersPerChild,
 [switch]$Mypy, [switch]$Force, [switch]$NoCarry, [string]$Output, [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.affected_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
