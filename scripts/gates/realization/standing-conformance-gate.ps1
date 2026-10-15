#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Standing conformance-spec corpus gate.

.DESCRIPTION
 Runs every committed conformance_gate.py spec under
 datrix/scripts/config/conformance-specs/ (top-level *.json files only --
 fixture subdirectories such as _fixtures/ are never spec sources and are
 never swept). Each spec's own self-test runs first, exactly as
 conformance_gate.py's single-spec CLI already guarantees on every
 invocation (main(): the self-test runs before any spec is evaluated,
 aborting with exit 2 before a real result is trusted) -- this wrapper adds
 no second self-test layer: conformance_gate.py --spec-dir runs the corpus.

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

.PARAMETER SelfTest
 Run only the runner's self-test (every assertion type detects and passes; an
 empty corpus and a rooted spec field are refused) and run no spec.

.EXAMPLE
 .\standing-conformance-gate.ps1
 Run every committed spec.

.EXAMPLE
 .\standing-conformance-gate.ps1 -SelfTest
 Run only the runner's self-test.

.EXAMPLE
 .\standing-conformance-gate.ps1 -Dbg
 Run every committed spec with debug logging.
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
if ($SelfTest) {
    $pythonArgs += "--self-test"
}
else {
    $pythonArgs += @("--spec-dir", (Join-Path $PSScriptRoot "..\..\config\conformance-specs"))
}
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\conformance_gate.py") -Arguments $pythonArgs -RequirePackages -Gate "standing-conformance")
