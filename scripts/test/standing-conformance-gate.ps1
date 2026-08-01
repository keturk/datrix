#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Standing conformance-spec corpus gate (D10).

.DESCRIPTION
 Runs every committed conformance_gate.py spec under
 datrix/scripts/config/conformance-specs/ (top-level *.json files only --
 fixture subdirectories such as _fixtures/ are never spec sources and are
 never swept). Each spec's own self-test runs first, exactly as
 conformance_gate.py's single-spec CLI already guarantees on every
 invocation (main(): the self-test runs before any spec is evaluated,
 aborting with exit 2 before a real result is trusted) -- this wrapper adds
 no second self-test layer, it only orchestrates one CLI call per spec.

 POLICY this wrapper exists to serve: a design-acceptance NEGATIVE check
 ("the old state is gone on every surface") that outlives its landing must
 either become a real test in the owning package (preferred, per the
 prefer-a-test-over-a-scratch-script rule), or a committed spec here --
 never a one-off run that nobody re-executes. When you land a change whose
 acceptance proof is "the old construct no longer exists anywhere", and
 that proof cannot naturally live as a package test, add a spec JSON here
 rather than running conformance_gate.py by hand once and discarding the
 command.

 PATH CONVENTION, enforced here before any spec runs: a committed spec's
 'target' and 'negative_control' must be RELATIVE to the spec file.
 conformance_gate.py accepts either form (an absolute path is fine for a
 one-off hand-run spec), but a committed absolute path bakes one machine's
 checkout location into the repo -- and since the runner hard-fails exit 2
 on a directory that does not exist, such a spec does not degrade
 gracefully elsewhere, it simply cannot run. Every spec in this corpus is
 therefore checked for rooted paths up front, and the whole sweep aborts
 (exit 2) naming the offenders rather than running a partial corpus.

 Negative-control fixtures live under scripts/config/conformance-specs/
 _fixtures/ -- per-spec in _fixtures/<spec-stem>/negative-control/, or in
 _fixtures/_shared/<name>/ when several specs police the same retired
 surface. A control tree is scanned with its assertion's own glob, so the
 fixture's filenames must satisfy that glob.

 Fails loud (exit 2) if the spec directory is missing or contains zero
 *.json files -- an empty corpus would make this gate vacuously pass.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (forwarded to conformance_gate.py as --debug).

.EXAMPLE
 .\standing-conformance-gate.ps1
 Run every committed spec.

.EXAMPLE
 .\standing-conformance-gate.ps1 -Dbg
 Run every committed spec with debug logging.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsRoot = Split-Path -Parent $scriptDir
$runnerScript = Join-Path $scriptsRoot "library\dev\conformance_gate.py"
$specsDir = Join-Path $scriptsRoot "config\conformance-specs"

$commonDir = Join-Path $scriptsRoot "common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: conformance_gate.py not found at: $runnerScript"
    exit 1
}

if (-not (Test-Path $specsDir)) {
    Write-Host "STANDING CONFORMANCE GATE CANNOT RUN: spec directory not found at $specsDir -- an empty/missing corpus would be a vacuous pass." -ForegroundColor Red
    exit 2
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

    $specs = Get-ChildItem -Path $specsDir -Filter "*.json" -File | Sort-Object Name
    if ($specs.Count -eq 0) {
        Write-Host "STANDING CONFORMANCE GATE CANNOT RUN: zero spec files directly under $specsDir -- an empty corpus would be a vacuous pass." -ForegroundColor Red
        exit 2
    }

    # Path convention (see .DESCRIPTION): a committed spec must address its
    # trees relative to itself, so the corpus runs from any checkout location.
    # Checked for the WHOLE corpus before any spec runs -- a portability defect
    # is a corpus-level fault, not a per-spec one.
    $rootedFields = @()
    foreach ($spec in $specs) {
        $spec_json = Get-Content -LiteralPath $spec.FullName -Raw | ConvertFrom-Json
        foreach ($field in @("target", "negative_control")) {
            $value = $spec_json.$field
            if ($value -is [string] -and [System.IO.Path]::IsPathRooted($value)) {
                $rootedFields += "$($spec.Name): '$field' = '$value'"
            }
        }
    }
    if ($rootedFields.Count -gt 0) {
        Write-Host "STANDING CONFORMANCE GATE CANNOT RUN: $($rootedFields.Count) committed spec field(s) use an absolute path. A committed spec must address its trees RELATIVE to the spec file, or the corpus only runs on the machine whose checkout path was baked in (the runner hard-fails on a missing directory)." -ForegroundColor Red
        foreach ($rooted in $rootedFields) {
            Write-Host "  $rooted" -ForegroundColor Red
        }
        exit 2
    }

    Write-Host "Running $($specs.Count) standing conformance spec(s)" -ForegroundColor Cyan

    $failures = 0
    foreach ($spec in $specs) {
        Write-Host ""
        Write-Host "--- $($spec.Name) ---" -ForegroundColor Cyan
        $pythonArgs = @($runnerScript, "--spec", $spec.FullName)
        if ($Dbg) { $pythonArgs += "--debug" }
        python @pythonArgs
        if ($LASTEXITCODE -ne 0) {
            $failures += 1
        }
    }

    Write-Host ""
    if ($failures -gt 0) {
        Write-Host "STANDING CONFORMANCE GATE FAILED: $failures of $($specs.Count) spec(s) failed." -ForegroundColor Red
        exit 1
    }

    Write-Host "STANDING CONFORMANCE GATE PASSED: all $($specs.Count) spec(s) green." -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
