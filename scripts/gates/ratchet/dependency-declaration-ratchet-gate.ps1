#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Dependency-declaration-only-path ratchet (W4 / design-principle F5 enforcement).

.DESCRIPTION
 Reports every site in every package implementing each registered language
 (its backend plus each language core the backend requires) that decides a
 dependency package NAME outside the language's own
 generation/dependency_tables.py table, and checks the out-of-table count
 against a decrease-only baseline at
 scripts/config/dependency-declaration-ratchet-baseline.json.

 Runs a built-in non-vacuity self-test on every invocation, including a
 fixture language split into a backend and a core, and a live check that
 every registered language's real catalog covers every package its real
 declared table names. Fails loud (exit 2) if fewer than two languages are
 registered.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER UpdateBaseline
 Write the live out-of-table count as the new baseline.

.EXAMPLE
 .\dependency-declaration-ratchet-gate.ps1
 Run the report over every registered language and check the ratchet.

.EXAMPLE
 .\dependency-declaration-ratchet-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\dependency-declaration-ratchet-gate.ps1 -UpdateBaseline
 Freeze the current live out-of-table count as the new baseline.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$UpdateBaseline
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Dbg) { $pythonArgs += "--debug" }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($UpdateBaseline) { $pythonArgs += "--update-baseline" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\dependency_declaration_ratchet.py") -Arguments $pythonArgs -RequirePackages -Gate "dependency-declaration-ratchet")
