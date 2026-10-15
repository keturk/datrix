#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Shared-RDBMS realization gate.

.DESCRIPTION
 A service that `uses` a shared container's RDBMS block realizes that block next to its own. For every
 registered `datrix.languages` target this gate GENERATES the shared-rdbms fixture (a shared container's
 block, a `readwrite` consumer that holds a seed and a `readonly` consumer) and applies language-neutral
 file-set assertions to the emitted tree: every consumer emits an entity module for the consumed block,
 every file of the owner's canonical migration chain appears byte for byte in every consumer, and the
 block's seed is emitted in the writer and in no reader. The behavioural assertions per language (typed
 access, read-only repositories, the chain lock key) live in each package's own tests.

 Derives the language set from `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded language list -- and refuses to pass (exit 2) with fewer than two registered languages.

 Runs a built-in non-vacuity self-test on every invocation, before trusting any real comparison: a planted
 language whose consumer emits no entity module, one whose carried chain differs from the canonical one,
 and one that seeds a reader must each be reported; a faithful planted language must report nothing; and a
 single-language run must be refused as vacuous.

 Repo-level validation script (per the datrix showcase boundary -- no pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison (no project is generated).

.EXAMPLE
 .\shared-rdbms-realization-gate.ps1
 Generate the fixture for every registered language and check the emitted trees.

.EXAMPLE
 .\shared-rdbms-realization-gate.ps1 -SelfTest
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\shared_rdbms_realization_gate.py") -Arguments $pythonArgs -RequirePackages -Gate "shared-rdbms-realization")
