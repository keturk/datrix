#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Migration upgrade-op family gate -- the cross-package half of the upgrade-op
 duplication census.

.DESCRIPTION
 The census behind this gate read the bodies of six _build_upgrade_op_for_*
 symbols across every migration target that defined them and pinned two
 conclusions:

   * The six are genuinely target-specific, not collapsible, so each target
     carrying the family must still define every one exactly once -- a later
     "cleanup" deleting one would be deleting a target's real behaviour.
   * One genuinely shared fact WAS hoisted: the targets reassembled the
     INDEX_ADDED JSON detail into its SnapshotIndex with byte-identical
     semantics and error text. That parse now lives once, in
     datrix_codegen_kernel.sql_facts.snapshot.migration_upgrade_op_index; each target
     must call it the exact number of times its own paths need, and none may
     redefine it.

 Structural resolution only, never a text match: call sites come from each
 module's import bindings, so an aliased import is followed and a same-suffix
 private wrapper is not miscounted -- both false-positive shapes have bitten
 this chain before, and both are proven every run by the built-in six-check
 non-vacuity self-test.

 The gate names no target: every registered datrix.languages package (its
 backend and each language core) is scanned, and which languages carry the
 family and how many shared-parser calls each one's paths make are reviewed
 facts in scripts/config/migration-upgrade-op-family-baseline.json. A language
 with no entry is held to no family and zero calls; a stale entry, an
 unrecorded carrier, and a baseline recording no carrier all fail.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix, and a unit test importing several generator packages to
 compare their bodies is the shape the import-boundary rule forbids outright).
 The shared parser's own input/output behaviour is a different question and
 stays as a unit test in datrix-codegen-common, which owns the function.

.PARAMETER Dbg
 Enable debug logging (names each self-test check as it passes).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\migration-upgrade-op-family-gate.ps1

.EXAMPLE
 .\migration-upgrade-op-family-gate.ps1 -SelfTest
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.ratchet.migration_upgrade_op_family_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
