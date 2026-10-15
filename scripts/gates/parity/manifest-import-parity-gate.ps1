#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Manifest / import parity gate -- declared Datrix dependencies equal imported ones.

.DESCRIPTION
 For every datrix-* package at the workspace root carrying a pyproject.toml,
 compares the datrix-* distributions its [project] dependencies declare against
 the datrix_* import roots its src/ tree actually imports. Both directions must
 be empty -- an undeclared import and a dead declaration are each a violation --
 and no runtime requirement may carry a test-only extra ([testkit], [dev],
 [testing]). Hard zero; no baseline.

 Exists because the shared editable venv makes every package importable from
 every other, so a manifest can lie in either direction with every suite green:
 a package documented as fenced out of the shared codegen layer imported it from
 a dozen production modules; a platform package ran on an undeclared dependency;
 three language packages carried a dead dependency; one package pulled a test
 extra into production. This gate is the set comparison that seam lacked.

 The package set is discovered from disk, never a hardcoded list. Runs a
 built-in non-vacuity self-test on every invocation (synthetic dirty and clean
 packages, plus a live-tree proof that the scanner sees a known real edge).

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO; prints each package's
 declared and imported sets).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\manifest-import-parity-gate.ps1
 Compare every datrix-* package's manifest against its imports.

.EXAMPLE
 .\manifest-import-parity-gate.ps1 -SelfTest
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\manifest_import_parity.py") -Arguments $pythonArgs -RequirePackages -Gate "manifest-import-parity")
