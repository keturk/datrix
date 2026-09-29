#!/usr/bin/env pwsh
<#
.SYNOPSIS
 D14 gate: no package's tests resolve a path inside another package's
 tests/ directory.

.DESCRIPTION
 AST-scans every .py file under every discovered datrix* package's tests/
 tree and statically evaluates the pathlib expressions test fixtures use to
 locate .dtrx/.dcfg/.json files (Path(__file__), .resolve(), .parent,
 .parents[N], "/" joins, and "from tests.<module> import NAME" -- always the
 same package's own tests/ namespace). Reports two things:

   (a) a resolved directory constant that points inside ANOTHER package's
       own tests/ tree (the D14 violation itself, regardless of whether the
       file it names still exists there);
   (b) a statically-resolved fixture path that does not exist on disk.

 This is exactly the shape that turned datrix-common commit 0badd1c's
 fixture cleanup into a red datrix-codegen-typescript suite:
 COMMON_FIXTURES_DIR / "system-with-jobs.dtrx" pointed at a file
 datrix-common's own tests no longer read, so nothing there knew to keep it.

 Packages are discovered from disk (any datrix* directory with a tests/
 tree) -- never a hardcoded list. Runs a built-in non-vacuity self-test on
 every invocation, which also plants both defect shapes in a temp tree and
 proves the scanner both finds and does not falsely find them, before
 checking a live read against the real workspace.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the scanner's self-test and exit, skipping the real workspace scan.

.PARAMETER ShowFiles
 Print each file as it is scanned.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\check-cross-package-fixture-reads.ps1
 Scan every package, fail on any cross-package reference or missing fixture.

.EXAMPLE
 .\check-cross-package-fixture-reads.ps1 -SelfTest
 Prove the scanner detects both defect shapes and clears the clean case.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "check-cross-package-fixture-reads.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: check-cross-package-fixture-reads.py not found at: $pythonScript"
    exit 2
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

trap {
    Write-Host ""
    Write-Warning "Interrupted by user (Ctrl-C)"
    Invoke-Cleanup
    exit 130
}

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }

    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"

    $pythonArgs = @($pythonScript)
    if ($BaseDir) { $pythonArgs += "--base-dir"; $pythonArgs += $BaseDir }
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($ShowFiles) { $pythonArgs += "--verbose" }

    if ($Dbg) {
        Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan
        Write-Host "Python script: $pythonScript" -ForegroundColor Cyan
    }

    & $pythonExe @pythonArgs
    $exitCode = $LASTEXITCODE
    Invoke-Cleanup
    exit $exitCode
}
catch {
    Write-Error "Error: $_"
    Invoke-Cleanup
    exit 1
}
