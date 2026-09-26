#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if a framework test suite compiles or executes generated output.

.DESCRIPTION
 A datrix-*/tests/ suite proves that DATRIX FUNCTIONALITY works -- that the
 generator emits the right thing. Whether the emitted output compiles and runs
 in its target language belongs to the generated tier: the generated project's
 own unit tests, and the deploy tests.

 Four shapes fail this gate:
   1. A toolchain subprocess -- javac / java / mvnw / dotnet / tsc / npm / npx /
      node / docker / az / gradle driven against generated output.
   2. In-process execution -- exec(compile(...)), runpy, or importlib's
      spec_from_file_location/exec_module applied to a rendered template.
   3. Suite-in-suite (pytest) -- a subprocess spawning a nested pytest session
      against a repo test path (pytest/py.test as argv[0], or the
      [sys.executable, "-m", "pytest", ...] module form).
   4. Suite-in-suite (script) -- a subprocess naming any script under
      datrix/scripts/ (directly, or via powershell -File), re-running a repo
      gate or metrics script a sibling gate already pays for.

 Both new shapes carve out pytester-based synthetic suites (a test function
 taking a pytester fixture parameter, or a direct pytester.runpytest*(...)
 attribute call) -- pytest's own plugin, which launches a nested run against a
 SYNTHETIC tree in a tmp dir, never against this repo's own production tests.

 Two shapes stay allowed: linters over generated TEXT (ruff/black -- reading is
 not executing), and subprocess runs of datrix itself (sys.executable -m
 datrix_cli, the import-boundary probes).

 The non-vacuity self-test runs on EVERY invocation before the real scan, so a
 green result can never mean "the detector was broken". Use -SelfTest to run
 only that leg.

.PARAMETER Suites
 Comma-separated tests/ directories to scan. When omitted, scans every
 datrix-* package's suite.

.PARAMETER Shapes
 Comma-separated violation kinds to report (default: all four). Use this to
 enforce the two new suite-in-suite shapes at hard zero independently of the
 pre-existing, still-red in-process-execution/toolchain-subprocess counts --
 e.g. -Shapes suite-in-suite-pytest,suite-in-suite-script. There is no
 baseline/exemption file for either new shape: both are hard zero.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.EXAMPLE
 .\toolchain-free-suites-gate.ps1
 Scan every package suite, every shape.

.EXAMPLE
 .\toolchain-free-suites-gate.ps1 -Suites D:/datrix/datrix-codegen-java/tests
 Scan a single suite.

.EXAMPLE
 .\toolchain-free-suites-gate.ps1 -Shapes suite-in-suite-pytest,suite-in-suite-script
 Enforce only the two new shapes at hard zero.

.EXAMPLE
 .\toolchain-free-suites-gate.ps1 -SelfTest
 Prove the detector fires on a planted compile call and spares an allowed one.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Suites = "",

    [Parameter()]
    [string]$Shapes = "",

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\toolchain_free_suites.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: toolchain_free_suites.py not found at: $runnerScript"
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
    if ($SelfTest) {
        $pythonArgs += "--self-test"
    }
    elseif (-not [string]::IsNullOrWhiteSpace($Suites)) {
        foreach ($item in $Suites.Split(",")) {
            $trimmed = $item.Trim()
            if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
                $pythonArgs += $trimmed
            }
        }
    }

    if (-not [string]::IsNullOrWhiteSpace($Shapes)) {
        $pythonArgs += "--shapes"
        $pythonArgs += $Shapes
    }

    $targetLabel = if ($SelfTest) { "self-test only" }
                   elseif ([string]::IsNullOrWhiteSpace($Suites)) { "all package suites" }
                   else { $Suites }
    $targetLabel = if ([string]::IsNullOrWhiteSpace($Shapes)) { $targetLabel } else { "$targetLabel (shapes: $Shapes)" }
    Write-Host "Running toolchain-free suite check for: $targetLabel" -ForegroundColor Cyan

    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Toolchain-free suite check failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Toolchain-free suite check passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
