#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Example-universe consistency and layout gate.

.DESCRIPTION
 Every system.dtrx under datrix/examples/ must appear in >= 1 named test set
 of datrix/scripts/config/test-projects.json, or carry a reviewed entry in
 datrix/scripts/config/test-set-exclusions.json. An unregistered example is
 never built by generate.ps1 -All / run-complete.ps1 -All, which select
 their corpus FROM test-projects.json's test sets -- exactly how the
 config-store and replayable-ingestion whole-example parked defects went
 unnoticed for a full generation cycle.

 Also enforces the examples tree's layout contract, since an example's
 identity IS its directory: no example may live inside another example, and
 no .dtrx/.dcfg may belong to two examples or to none.

 Runs a built-in non-vacuity self-test on every invocation (a pure
 comparator proof against synthetic ids and paths, no file I/O). Fails loud
 (exit 2) if zero examples exist on disk.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\example-registry-gate.ps1
 Run the gate against the real tree.

.EXAMPLE
 .\example-registry-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Dbg) { $pythonArgs += "--debug" }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\example_registry_consistency.py") -Arguments $pythonArgs -RequirePackages -Gate "example-registry")
