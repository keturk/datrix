#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Shared-RDBMS realization gate.

.DESCRIPTION
 A service that `uses` a shared container's RDBMS block realizes that block next to its own. For every
 registered `datrix.languages` target this gate GENERATES the shared-rdbms fixture (a shared container's
 block, a `readwrite` consumer that holds a seed and a `readonly` consumer) and applies language-neutral
 file-set assertions to the emitted tree: every consumer emits an entity module for the consumed block,
 and the block's seed is emitted in the writer and in no reader. The behavioural assertions per language
 (typed access, read-only repositories, the seed lock key) live in each package's own tests.

 Derives the language set from `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded language list -- and refuses to pass (exit 2) with fewer than two registered languages.

 Runs a built-in non-vacuity self-test on every invocation, before trusting any real comparison: a planted
 language whose consumer emits no entity module, one that seeds a reader, and one whose writer emits no
 seed must each be reported; a faithful planted language must report nothing; and a
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
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.realization.shared_rdbms_realization_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
