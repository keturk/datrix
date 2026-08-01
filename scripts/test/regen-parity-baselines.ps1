#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Re-bless the reference-example parity baselines. THE single re-bless command.

.DESCRIPTION
  Regenerates the stored baselines consumed by reference-example-parity-gate.ps1.
  For the corpus example it runs the REAL generation pipeline (the same code path
  generate.ps1 runs) ONCE PER REGISTERED datrix.languages TARGET (never a hardcoded
  python/typescript literal) and writes a per-file sha256 manifest of each language's
  generated output tree to:

      datrix/scripts/config/parity-baselines/<example_id>/<language>.sha256

  This is the ONLY sanctioned baseline writer -- the gate never writes baselines
  (no auto-heal). Run it deliberately, AFTER you have explained the change.

  ONE-EXAMPLE CORPUS. The gate checks a single reference example
  (PARITY_EXAMPLE_RELPATH in scripts/library/test/reference_example_parity.py), so a
  re-bless writes that example's baseline once per registered language. Re-blessing
  is correspondingly cheap, and its blast radius is one baseline directory rather
  than every example's tree.

  The full generated tree of each blessed example is kept under
  .test-output/parity-baseline-cache/, so that when the gate later fails it can show
  you a real unified diff of what changed rather than only a sha256 mismatch.

  An example that cannot generate is NOT blessed: the run fails and names it. Add it
  to scripts/config/parity-known-nongenerating.json (with a reason and a bumped
  expected_count) only when the defect is genuine, pre-existing, and tracked.

  Every successful bless (whether the default corpus example or an explicit
  -Example target) also updates scripts/config/parity-blessed-count.json --
  the grow-only ratchet the check gate uses to detect a baseline silently
  deleted outside this script (D8.1). A partial bless (any example/language
  pair failed to generate) writes nothing, ratchet included.

.PARAMETER Example
  Path relative to datrix/examples/ for a single example. Omit to re-bless the gate's
  corpus example. An explicit value may name ANY example, corpus member or not --
  ingress-migration-conformance-gate.ps1 blesses the identity example this way as its
  own byte-level proof, and narrowing the corpus must not take that away.

.PARAMETER Dbg
  Enable DEBUG-level logging (very verbose: the pipeline logs every stage).

.EXAMPLE
  .\regen-parity-baselines.ps1
  Re-bless the corpus example, once per registered language, after an intentional
  and reviewed change to generated output.

.NOTES
  Exit codes: 0 = all selected baselines written, 1 = an example failed to generate,
  2 = usage or config error.

  ALWAYS review the resulting baseline diff before committing. An unexpected baseline
  change is a generator regression, not a baseline update.

  The blessed-coverage ratchet (scripts/config/parity-blessed-count.json) is
  updated by this script alone, in the same operation as any successful
  bless -- never hand-edit that file.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Example,

    [Alias("Dbg")]
    [switch]$DebugLogging
)

# See reference-example-parity-gate.ps1 for why this is "Continue", not "Stop".
$ErrorActionPreference = "Continue"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$scriptsRoot = Split-Path -Parent $scriptDir
$libraryDir = Join-Path $scriptsRoot "library"
$commonDir = Join-Path $scriptsRoot "common"
$runnerScript = Join-Path $libraryDir "test\reference_example_parity.py"

Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path -LiteralPath $runnerScript)) {
    Write-Error "reference_example_parity.py not found at: $runnerScript"
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
    Ensure-DatrixPackagesInstalled -SkipIfInstalled

    $pythonArgs = @($runnerScript, "--mode", "bless")
    if ($Example) {
        $pythonArgs += "--example"
        $pythonArgs += $Example
    }
    if ($DebugLogging) {
        $pythonArgs += "--debug"
    }

    $scope = if ($Example) { "example=$Example" } else { "the corpus example" }
    Write-Host "Re-blessing parity baselines: $scope" -ForegroundColor Cyan
    Write-Host ""

    python @pythonArgs
    $exitCode = $LASTEXITCODE

    Write-Host ""
    if ($exitCode -ne 0) {
        Write-Host "Parity baseline re-bless FAILED (exit code $exitCode)." -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Parity baselines re-blessed." -ForegroundColor Green
    Write-Host "IMPORTANT: review the baseline diff before committing." -ForegroundColor Yellow
    Write-Host "An unexpected baseline change is a generator regression, not a baseline update." -ForegroundColor Yellow
    exit 0
}
finally {
    Invoke-Cleanup
}
