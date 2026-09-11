#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Shared-builder reachability gate -- every public build_* function in
 datrix-codegen-common must have a production caller.

.DESCRIPTION
 Every module-level build_* function declared in datrix_codegen_common's
 algorithms/ and context_models/ modules must be called from somewhere outside
 its own defining module, across the defining package itself, every registered
 language package, and datrix-cli. A shared context builder that is written,
 exported and unit-tested but never called looks complete by every signal
 except the one that matters: it never executes on a real generation run.

 Whole-tree AST import/call-graph resolution, never text matching. It follows
 aliased imports (import X as Y, from X import Y as Z), attribute calls
 (module.build_x(...)), and package __init__ re-exports; and it counts a THIN
 DELEGATION as live -- a wrapper whose entire body is one context construction
 delegating to a callee some module outside the defining package binds, and
 whose constructed type another production module builds. A builder that
 branches, walks the model, logs, or returns None is never a thin delegation,
 which is what keeps that rule from rescuing a genuinely orphaned builder.

 Hard zero: no exemption file, no pinned baseline. A baseline on a gate whose
 whole job is "notice code nobody wired in" would exempt exactly the defect
 class it exists to catch. When it is red, wire the named function into its
 consuming package(s)/orchestrator, or delete it.

 The language package set comes from the installed datrix.languages entry
 points at run time -- never a literal list -- and the gate refuses to run
 against fewer than two of them rather than passing vacuously. Runs a built-in
 five-check non-vacuity self-test on every invocation, before any real census
 is trusted.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix, and a unit test importing several generator packages
 is the cross-package coupling the import-boundary rule forbids).

.PARAMETER Dbg
 Enable debug logging (names each self-test check as it passes).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real census.

.PARAMETER Census
 Print the reachability census -- every builder with its calling packages,
 every live thin delegation with the delegate and context type it resolved
 through, and every dead builder -- and exit 0. A measurement, not a verdict.

.EXAMPLE
 .\shared-builder-reachability-gate.ps1
 Run the gate over the real installed package tree.

.EXAMPLE
 .\shared-builder-reachability-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\shared-builder-reachability-gate.ps1 -Census
 Report the reachability census without rendering a verdict.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Census
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\shared_builder_reachability.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: shared_builder_reachability.py not found at: $runnerScript"
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
    if ($Census) {
        $pythonArgs += "--census"
    }

    Write-Host "Running shared-builder reachability gate (every registered language package + datrix-cli)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Shared-builder reachability gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Shared-builder reachability gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
