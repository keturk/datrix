#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Pooled-cache member-slice realization gate.

.DESCRIPTION
 For every registered `datrix.languages` / `datrix.platforms` target, asserts
 that a pooled cache member's declared slice (`PooledMember.slice_index`,
 `datrix_codegen_kernel.pooling.contract`) actually reaches that target's own
 emitted-output-facing source -- never merely that the shared pooling
 pre-pass computed it. Detection is STATIC: this gate parses each target
 package's own `src/` tree (Python `ast`, never a substring/regex scan) for a
 function that both reads a `.slice_index` attribute and is call-reachable
 from elsewhere in that same tree (declared AND consumed, not dead code). It
 never invokes `generate.ps1` and never generates a project.

 A target that does not yet realize the slice must carry a typed exemption
 (axis + target + reason) in
 `datrix/scripts/config/pooled-cache-realization-exemptions.json` --
 a target quietly losing its realization fails the gate the same way a
 target that never had one does.

 Derives its target sets from
 `importlib.metadata.entry_points(group="datrix.languages" | "datrix.platforms")`
 at runtime -- never a hardcoded language-name or
 aws/azure/docker literal -- so a future datrix-codegen-<x> package is
 covered automatically with no edit to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: a synthetic declared-and-reachable `.slice_index`
 consumer must classify realized; a synthetic declared-but-dead (never
 called) one must classify NOT realized; a synthetic single-target axis must
 be refused as vacuous. Fails loud (exit 2) if fewer than 2 targets are
 registered on an axis being checked.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Axis
 Which axis to check: "languages" or "platforms". Omit to check BOTH axes
 in one invocation.

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\pooled-cache-realization-gate.ps1
 Run the gate for every registered language AND platform target.

.EXAMPLE
 .\pooled-cache-realization-gate.ps1 -Axis platforms
 Run the gate for the platforms axis only.

.EXAMPLE
 .\pooled-cache-realization-gate.ps1 -SelfTest
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
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.realization.pooled_cache_realization_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
