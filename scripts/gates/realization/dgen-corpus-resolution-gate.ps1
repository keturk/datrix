#!/usr/bin/env pwsh
<#
.SYNOPSIS
 DAL generator corpus reference-resolution gate.

.DESCRIPTION
 Proves the real, shipped corpus of builder/call/context/appends references
 across every DISCOVERED DAL generator target -- derived from
 datrix.dgen_generator_targets + datrix.platforms entry-point discovery,
 never a hardcoded package list -- is genuinely resolvable. Compiles each
 target's DAL generator definitions through target_definitions(<target>), one
 subprocess per target -- the compile succeeding IS the assertion; a bad
 reference raises DalReferenceError there.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix): the proof spans every concrete target package, which
 datrix_codegen_common may not import and no package's own suite may span.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the self-test: a planted definitions package naming a builder its
 namespace lacks is reported as an unresolved reference, its twin naming a
 real builder resolves, and the per-target compile reaches a shipped corpus.

.EXAMPLE
 .\dgen-corpus-resolution-gate.ps1
 Run the gate for every discovered DAL generator target.

.EXAMPLE
 .\dgen-corpus-resolution-gate.ps1 -SelfTest
 Run only the self-test.
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\dgen_corpus_resolution.py") -Arguments $pythonArgs -RequirePackages -Gate "dgen-corpus-resolution")
