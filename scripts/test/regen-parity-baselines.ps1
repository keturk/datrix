#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Re-bless the reference-example parity baselines. THE single re-bless command.

.DESCRIPTION
  Regenerates the stored baselines consumed by reference-example-parity-gate.ps1.
  For each selected example it runs the REAL generation pipeline (the same code path
  generate.ps1 runs) and writes a per-file sha256 manifest of the whole generated
  output tree to:

      datrix/scripts/config/parity-baselines/<example_id>/<language>.sha256

  This is the ONLY sanctioned baseline writer -- the gate never writes baselines
  (no auto-heal). Run it deliberately, AFTER you have explained the change.

  PER-EXAMPLE GRANULARITY. An intentional change that affects one example re-blesses
  ONE example: `-Example "01-foundation"`. There is no need to re-bless all of them.

  The full generated tree of each blessed example is kept under
  .test-output/parity-baseline-cache/, so that when the gate later fails it can show
  you a real unified diff of what changed rather than only a sha256 mismatch.

  An example that cannot generate is NOT blessed: the run fails and names it. Add it
  to scripts/config/parity-known-nongenerating.json (with a reason and a bumped
  expected_count) only when the defect is genuine, pre-existing, and tracked.

.PARAMETER Example
  Path relative to datrix/examples/ for a single example (e.g. "01-foundation" or
  "02-features/01-core-data-modeling/entities"). Omit to re-bless every example.

.PARAMETER Dbg
  Enable DEBUG-level logging (very verbose: the pipeline logs every stage).

.EXAMPLE
  .\regen-parity-baselines.ps1 -Example "01-foundation"
  Re-bless one example after an intentional, reviewed change to its output.

.EXAMPLE
  .\regen-parity-baselines.ps1
  Re-bless every example (only for a change that legitimately moves all output).

.NOTES
  Exit codes: 0 = all selected baselines written, 1 = an example failed to generate,
  2 = usage or config error.

  ALWAYS review the resulting baseline diff before committing. An unexpected baseline
  change is a generator regression, not a baseline update.
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

    $scope = if ($Example) { "example=$Example" } else { "ALL examples" }
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
