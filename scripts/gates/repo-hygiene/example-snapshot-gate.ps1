#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Committed example-snapshot gate.

.DESCRIPTION
 Every directory directly under any datrix/examples/**/generated/ must be named
 <language>-<platform> with both halves registered (datrix.languages /
 datrix.platforms entry points), and each example must carry one snapshot per
 registered language for every platform it carries. Every dotted datrix_*
 reference in every snapshot text file and in every datrix-*/src .j2 template
 must resolve through importlib.

 Targets come from the registered entry points at run time, never from a
 hand-written list. Refuses (exit 2) with fewer than two registered languages,
 with no snapshot on disk, or when no template reference is found.

 Runs a built-in non-vacuity self-test on every invocation. Does not
 regenerate: refresh a snapshot with generation\refresh-example-snapshot.ps1.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\example-snapshot-gate.ps1
 Run the gate against the real tree.

.EXAMPLE
 .\example-snapshot-gate.ps1 -SelfTest
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\example_snapshots.py") -Arguments $pythonArgs -RequirePackages -Gate "example-snapshot")
