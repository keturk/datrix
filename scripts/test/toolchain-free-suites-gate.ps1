#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if a framework test suite compiles or executes generated output.

.DESCRIPTION
 A datrix-*/tests/ suite proves that DATRIX FUNCTIONALITY works -- that the
 generator emits the right thing. Whether the emitted output compiles and runs
 in its target language belongs to the generated tier: the generated project's
 own unit tests, and the deploy tests.

 Two shapes fail this gate:
   1. A toolchain subprocess -- javac / java / mvnw / dotnet / tsc / npm / npx /
      node / docker / az / gradle driven against generated output.
   2. In-process execution -- exec(compile(...)), runpy, or importlib's
      spec_from_file_location/exec_module applied to a rendered template.

 Two shapes stay allowed: linters over generated TEXT (ruff/black -- reading is
 not executing), and subprocess runs of datrix itself (sys.executable -m
 datrix_cli, the import-boundary probes).

 The non-vacuity self-test runs on EVERY invocation before the real scan, so a
 green result can never mean "the detector was broken". Use -SelfTest to run
 only that leg.

.PARAMETER Suites
 Comma-separated tests/ directories to scan. When omitted, scans every
 datrix-* package's suite.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.EXAMPLE
 .\toolchain-free-suites-gate.ps1
 Scan every package suite.

.EXAMPLE
 .\toolchain-free-suites-gate.ps1 -Suites D:/datrix/datrix-codegen-java/tests
 Scan a single suite.

.EXAMPLE
 .\toolchain-free-suites-gate.ps1 -SelfTest
 Prove the detector fires on a planted compile call and spares an allowed one.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Suites = "",

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

    $targetLabel = if ($SelfTest) { "self-test only" }
                   elseif ([string]::IsNullOrWhiteSpace($Suites)) { "all package suites" }
                   else { $Suites }
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
