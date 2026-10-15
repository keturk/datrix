#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Capability gap ledger gate.

.DESCRIPTION
 Censuses every registered target's `capability_gaps` rows (languages, client
 targets and platforms, read off the live declarations), enforces a
 decrease-only two-directional pin on the total and the per-target split
 (`scripts/config/capability-gap-baseline.toml`), and fails when EVERY distinct
 implementation of an axis carries a row for the same surface -- a defect in the
 shared layer, never a per-target gap. A row suppresses nothing elsewhere; this
 gate only counts and bounds the ledger. The row count is printed on every run.

 Derives its target sets from the installed `datrix.languages`,
 `datrix.generators` (client targets) and `datrix.platforms` entry points at
 runtime -- never a hardcoded target literal. Registered names that share one
 on-disk package fold into one implementation.

 Runs a built-in non-vacuity self-test on every invocation, before trusting any
 real census. Fails loud (exit 2) if an axis has fewer than 2 distinct
 implementations or the baseline is unreadable.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Debug logging: prints every censused row (target, surface, detail).

.PARAMETER SelfTest
 Run only the built-in non-vacuity self-test; skip the real census.

.PARAMETER BaselinePath
 Compare against this baseline TOML instead of the committed one (used to prove
 a raised or lowered pin fails).

.EXAMPLE
 .\capability-gap-ledger-gate.ps1
 Run the gate for every registered target.

.EXAMPLE
 .\capability-gap-ledger-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [string]$BaselinePath
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Dbg) { $pythonArgs += "--debug" }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($BaselinePath) { $pythonArgs += @("--baseline", $BaselinePath) }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\capability_gap_ledger.py") -Arguments $pythonArgs -RequirePackages -Gate "capability-gap-ledger")
