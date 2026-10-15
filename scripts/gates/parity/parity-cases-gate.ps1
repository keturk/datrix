#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Parity cases gate: every parity row, read on every registered target of its axis.

.DESCRIPTION
 Loads every row of gates\parity\cases\*.parity.yaml through the case schema and the
 parity row checks, discovers the targets from the installed entry points (a row whose
 probe LanguageConformanceProbes declares is read on every registered language, one
 PlatformConformanceProbes declares on every registered platform), builds each fixture
 once per target (an example generated through the real pipeline, an enum the example
 declares, or a web-security header-set fixture), reads each target through its own
 conformance probes, and compares every reading with the row's authored expectation.

 A target whose reading differs from the expectation is a DIVERGENCE (so every target
 agreeing on a wrong value fails); a DRIFT line names every target's reading when they
 differ from each other. A target carrying the row's capability gap is a GAP.

 Runs a self-test on every invocation before any real row: the gate names no target,
 two planted targets give two readings per row, one divergent target is exactly one
 failure, an agreed wrong value fails, a missing probe method and a single target stop
 the run, a planted fixture path never reaches the report, and the tag selection obeys
 test.ps1's ceiling.

 Repo-level validation script (per the datrix showcase boundary -- no pytest suite
 lives in datrix).

.PARAMETER Tag
 Comma-separated feature tags: read only the rows carrying one of them (at most three,
 each carried by some row). Without -Tag every row is read: the whole corpus, Jon's run.

.PARAMETER SelfTest
 Run only the self-test; read no row and generate nothing.

.PARAMETER Dbg
 Debug logging, including the text of a fixture or probe failure.

.EXAMPLE
 .\parity-cases-gate.ps1 -Tag rest-api
 Read the route rows on every registered language.

.EXAMPLE
 .\parity-cases-gate.ps1 -SelfTest
 Run only the self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Tag,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Tag) { $pythonArgs += @("--tag", $Tag) }
if ($Dbg) { $pythonArgs += "--debug" }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\parity_cases.py") -Arguments $pythonArgs -RequirePackages -Gate "parity-cases")
