#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Source comment-reference gate.

.DESCRIPTION
 Every module a comment or docstring in a framework package's src/ tree cites
 must exist. Dotted datrix_* references resolve through importlib. A bare or
 relative file citation (foo.py, a/b/foo.py) must name a .py file of the citing
 package or of a package in its runtime dependency closure, or a file the
 generators emit; a module of any other package is cited by its anchored path
 (datrix-<package>/src/...) or dotted import path, which must resolve.

 Packages, dependencies and emitted file names are read from disk at run time,
 never from a hand-written list. No baseline and no exemption file: the
 terminal state is zero.

 Runs a built-in non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.EXAMPLE
 .\source-comment-reference-gate.ps1
 Scan every framework package's src/ comments and docstrings.

.EXAMPLE
 .\source-comment-reference-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
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
$runnerScript = Join-Path $scriptDir "lib\source_comment_references.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: source_comment_references.py not found at: $runnerScript"
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
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }

    Write-Host "Running source comment-reference gate" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Source comment-reference gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Source comment-reference gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
