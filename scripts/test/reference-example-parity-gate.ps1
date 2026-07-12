#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Reference-example parity gate: proves generated output has not changed unintentionally.

.DESCRIPTION
  For every example system.dtrx under datrix/examples/, runs the REAL generation
  pipeline (datrix_cli.pipeline.generation.GenerationPipeline -- the same code path
  generate.ps1 runs, with the same PipelineConfig defaults) and compares a per-file
  sha256 manifest of the whole generated output tree against the stored baseline in
  datrix/scripts/config/parity-baselines/<example_id>/<language>.sha256.

  Any changed byte in any generated file, and any file that appears or disappears,
  fails the gate. This is the repo's only automated proof behind the "generated
  output is byte-identical" acceptance property.

  ONE LANGUAGE PER EXAMPLE. The generator reads the target language from each
  project's config/system.dcfg (generate.ps1's -L flag only labels the output path),
  so each example is generated exactly once, in its declared language. This gate does
  NOT enumerate languages and does NOT run a language matrix.

  NON-VACUITY. Every run first proves the comparator bites: it copies a genuinely
  generated tree, mutates one byte of one file, and requires that the comparison
  reports exactly that path as CHANGED with a rendered unified diff. If the
  comparator cannot detect a real change, the gate fails regardless of the examples.

  FAILURE OUTPUT names every changed/added/removed path and, when a local baseline
  cache from the last bless is present, renders a real unified diff of each changed
  file. The freshly generated tree is left under .test-output/parity-current/.

  KNOWN NON-GENERATING examples (real, pre-existing, tracked defects) are listed in
  scripts/config/parity-known-nongenerating.json with a pinned count and are reported
  loudly on every run -- never silently skipped.

  Repo-level validation script, not a pytest suite (CLAUDE.md: "Repo-level validation
  = scripts, not pytest"), and datrix_codegen_common may not import datrix_cli.

.PARAMETER Example
  Path relative to datrix/examples/ for a single example (e.g. "01-foundation" or
  "02-features/01-core-data-modeling/entities"). Omit to check every example.

.PARAMETER Dbg
  Enable DEBUG-level logging (very verbose: the pipeline logs every stage).

.EXAMPLE
  .\reference-example-parity-gate.ps1
  Check every example against its stored baseline.

.EXAMPLE
  .\reference-example-parity-gate.ps1 -Example "01-foundation"
  Check one example (fast iteration while changing a generator).

.NOTES
  Exit codes: 0 = every example matches its baseline (and the comparator is
  non-vacuous), 1 = drift / missing baseline / generation failure / self-test
  failure, 2 = usage or config error.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Example,

    [Alias("Dbg")]
    [switch]$DebugLogging
)

# NOTE: deliberately "Continue", not "Stop". This script shells out to `python`;
# on Windows PowerShell 5.1 any line Python's logging writes to stderr is wrapped
# in a NativeCommandError and, under "Stop", aborts the script mid-run. Pass/fail
# is taken from the child's explicit exit code ($LASTEXITCODE) below.
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

    $pythonArgs = @($runnerScript, "--mode", "check")
    if ($Example) {
        $pythonArgs += "--example"
        $pythonArgs += $Example
    }
    if ($DebugLogging) {
        $pythonArgs += "--debug"
    }

    $scope = if ($Example) { "example=$Example" } else { "all examples" }
    Write-Host "Reference-example parity gate: $scope" -ForegroundColor Cyan
    Write-Host ""

    python @pythonArgs
    $exitCode = $LASTEXITCODE

    Write-Host ""
    if ($exitCode -eq 0) {
        Write-Host "Reference-example parity gate PASSED." -ForegroundColor Green
    }
    else {
        Write-Host "Reference-example parity gate FAILED (exit code $exitCode)." -ForegroundColor Red
        Write-Host "Explain every diff before re-blessing. An unexplained diff is a bug, not a baseline update." -ForegroundColor Yellow
    }
    exit $exitCode
}
finally {
    Invoke-Cleanup
}
