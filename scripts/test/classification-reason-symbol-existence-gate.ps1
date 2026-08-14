#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Classification-reason symbol-existence gate.

.DESCRIPTION
    Asserts that every code symbol and `file.py:NN` citation appearing in any
    `reason` or `collapsibility.reason` in either drift-classification file
    resolves to something that exists in the live `src/` trees of the packages on
    that axis. This is a naming-shape heuristic over backtick-quoted spans, not
    semantic analysis: under-reporting an exotic reference phrased outside that
    shape is a known, accepted, documented limitation (see
    classification_reason_symbol_existence.py's module docstring); a hardcoded
    per-entry allowlist is NOT accepted in its place.

    Resolution searches three surfaces scoped to the axis's own target package
    src trees: real Python identifiers, string-literal content parsed from those
    same .py files, and raw Jinja (.j2) template text -- because many citations
    name a construct in the GENERATED target language (a C# `using` statement,
    EF Core's `FirstOrDefaultAsync`) that Datrix's own Python source never
    declares as one of its own functions/classes/attributes. A dotted citation
    whose base names a real class is checked strictly against that class's own
    declared/assigned attributes -- a class existing does not launder a
    nonexistent attribute cited on it.

    Runs a built-in plant/observe/revert non-vacuity self-test on every invocation.

    Repo-level validation script (per the datrix showcase boundary -- no pytest
    suite lives in datrix).

.PARAMETER Axis
    Which classification file to check: "languages" (default) or "platforms".

.PARAMETER Dbg
    Enable debug logging.

.PARAMETER SelfTest
    Run only the non-vacuity self-test and skip the real check.

.EXAMPLE
    .\classification-reason-symbol-existence-gate.ps1
    Check the language-axis classification file.

.EXAMPLE
    .\classification-reason-symbol-existence-gate.ps1 -Axis platforms -SelfTest
    Run only the platform-axis self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [ValidateSet("languages", "platforms")]
    [string]$Axis = "languages",

    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\classification_reason_symbol_existence.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: classification_reason_symbol_existence.py not found at: $runnerScript"
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

    $pythonArgs = @($runnerScript, "--axis", $Axis)
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }

    Write-Host "Running classification-reason symbol-existence gate on the $Axis axis" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Classification-reason symbol-existence gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Classification-reason symbol-existence gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
