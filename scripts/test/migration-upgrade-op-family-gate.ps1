#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Migration upgrade-op family gate -- the cross-package half of the upgrade-op
 duplication census.

.DESCRIPTION
 The census behind this gate read both bodies of six _build_upgrade_op_for_*
 symbols across the two targets that define them (python's Alembic migration
 generator and dotnet's FluentMigrator ops) and pinned two conclusions:

   * Five of the six are genuinely divergent, not collapsible. Each entry in
     parallel-implementation-drift-classification.json carries
     collapsibility.mechanism = "none" with its own reason, and BOTH private
     copies must still exist -- a later "cleanup" deleting one would be
     deleting a target's real behaviour. The _build_upgrade_op_for_field_added
     entry additionally recorded a behaviour gap that is now CLOSED (dotnet
     emitted no backfill default, so a safe non-nullable FIELD_ADDED rendered a
     migration that failed at apply time on a populated table); the gate holds
     both halves of that -- the entry's `intentional` status, and the
     default-bearing FluentMigratorColumn field that earns it.
   * One genuinely shared fact WAS hoisted: both targets reassembled the
     INDEX_ADDED JSON detail into its SnapshotIndex with byte-identical
     semantics and error text. That parse now lives once, in
     datrix_codegen_common.algorithms.migration_upgrade_op_index; each target
     must call it the exact number of times its own paths need, and neither may
     redefine it.

 Structural resolution only, never a text match: call sites come from each
 module's import bindings, so an aliased import is followed and a same-suffix
 private wrapper is not miscounted -- both false-positive shapes have bitten
 this chain before, and both are proven every run by the built-in six-check
 non-vacuity self-test.

 The two languages are named (a fact about which targets carry this family, not
 a claim about which targets exist) but their packages resolve through the
 installed datrix.languages entry points, so a named language that is not
 installed fails loud instead of letting its half pass vacuously.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix, and a unit test importing two generator packages to
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

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\migration_upgrade_op_family.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: migration_upgrade_op_family.py not found at: $runnerScript"
    exit 1
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

trap {
    Invoke-Cleanup
    break
}

Ensure-DatrixVenv

try {
    Ensure-DatrixPackagesInstalled

    $pythonArgs = @($runnerScript)
    if ($Dbg) {
        $pythonArgs += "--debug"
    }
    if ($SelfTest) {
        $pythonArgs += "--self-test"
    }

    Write-Host "Running migration upgrade-op family gate (classification pins + shared INDEX_ADDED parse)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Migration upgrade-op family gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Migration upgrade-op family gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
