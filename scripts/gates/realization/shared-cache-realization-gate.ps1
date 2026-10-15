#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Shared-cache realization gate.

.DESCRIPTION
 A service that `uses` a shared cache container realizes that container's cache block next to its
 own. For every registered `datrix.languages` target this gate asserts the target's source walks
 `realized_cache_blocks` (so every realized block gets a connection, typed access and operations),
 and for every registered `datrix.platforms` target it asserts the source walks the same set AND
 calls `require_cache_keys_supplied` (so every connection key the surface declares is supplied).
 Detection is STATIC: it parses each target's own `src/` trees (the backend package plus every
 language core it requires) with Python `ast`, and never generates a project. The behavioural
 assertions per language and platform live in each package's own tests.

 Derives both target sets from
 `importlib.metadata.entry_points(group="datrix.languages" | "datrix.platforms")` at runtime --
 never a hardcoded language or platform list -- and refuses to pass (exit 2) with fewer than two
 targets on an axis.

 Runs a built-in non-vacuity self-test on every invocation, before trusting any real comparison:
 a planted consumer-blind source tree (reads only the service's own cache block) must be detected,
 a tree that walks the realized blocks must classify realized, and a single-target axis must be
 refused as vacuous.

 Repo-level validation script (per the datrix showcase boundary -- no pytest suite lives in datrix).

.PARAMETER Axis
 Which axis to check: "languages" or "platforms". Omit to check BOTH axes in one invocation.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\shared-cache-realization-gate.ps1
 Run the gate for every registered language AND platform target.

.EXAMPLE
 .\shared-cache-realization-gate.ps1 -Axis platforms
 Run the gate for the platforms axis only.

.EXAMPLE
 .\shared-cache-realization-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet("languages", "platforms")]
    [string]$Axis,

    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Axis) { $pythonArgs += @("--axis", $Axis) }
if ($Dbg) { $pythonArgs += "--debug" }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\shared_cache_realization_gate.py") -Arguments $pythonArgs -RequirePackages -Gate "shared-cache-realization")
