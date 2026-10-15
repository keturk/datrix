#!/usr/bin/env pwsh
<#
.SYNOPSIS
 DAL generator corpus reference-resolution gate.

.DESCRIPTION
 Proves the real, shipped corpus of builder/call/context/appends references
 across every DISCOVERED DAL generator target -- derived from
 datrix.dgen_generator_targets + datrix.platforms entry-point discovery,
 never a hardcoded package list -- is genuinely resolvable. Imports each
 target's DAL generator definitions module -- import succeeding IS the assertion;
 a bad reference raises DalReferenceError at import time.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix). Previously a pytest test inside datrix-codegen-common
 that imported all seven concrete target packages directly, which was both a
 cross-package import boundary violation (datrix_codegen_common must not
 import concrete target packages) and a cross-package test (prohibited
 everywhere in the repo). Moved here as the repo-level proof it always was.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the self-test: a planted definitions package naming a builder its
 namespace lacks is reported as an unresolved reference, and its twin naming a
 real builder resolves.

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
