#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Shared-home body gate: no function outside a shared home may carry the body of a public shared-home function.

.DESCRIPTION
 Wraps datrix/scripts/gates/parity/lib/shared_home_bodies.py. AST-walks every public function of
 datrix-common, datrix-codegen-kernel and datrix-codegen-common and every function of every other
 datrix-* package's src/ tree. A function qualifies at 8 lines and 40 AST nodes; its body is
 normalized (docstring, annotations and decorators dropped, parameter and local names renamed to
 positional tokens, constants collapsed to their type; attribute names and call targets kept). A
 function whose normalized body equals a public home function's in another package is a hit. The
 verdict is a per-package count against the decrease-only pin in
 datrix/scripts/config/shared-home-body-baseline.toml: an increase fails, a decrease passes.

 Runs a plant / observe / revert self-test on every invocation before any real scan is trusted.
 Exits 2 on a self-test failure, an unreadable baseline, an unparseable source file or a missing
 home package.

.PARAMETER Hits
 Print every hit line (copy location and name == home location and name).

.PARAMETER Symbol
 Comma-separated or repeated bare function names; print only the hit lines whose copy has one of
 these names. A report filter only: it never changes the count or the exit code.

.PARAMETER UpdateBaseline
 Seed the baseline from this run when it does not exist; otherwise lower every package's count to
 the live value (keeping seed and reason). Refuses, exit 1, when any count would rise.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the self-test and skip the real scan.

.EXAMPLE
 .\shared-home-body-gate.ps1

.EXAMPLE
 .\shared-home-body-gate.ps1 -Hits

.EXAMPLE
 .\shared-home-body-gate.ps1 -Symbol event_for_replay_plan,_iter_calls
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Hits,

    [Parameter()]
    [string[]]$Symbol,

    [Parameter()]
    [switch]$UpdateBaseline,

    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runnerScript = Join-Path $scriptDir "lib\shared_home_bodies.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: shared_home_bodies.py not found at: $runnerScript"
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
    if ($Hits) { $pythonArgs += "--show-hits" }
    if ($Symbol) { $pythonArgs += "--symbol"; $pythonArgs += ($Symbol -join ",") }
    if ($UpdateBaseline) { $pythonArgs += "--update-baseline" }
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }

    Write-Host "Running shared-home body gate" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Shared-home body gate failed (exit code $exitCode)" -ForegroundColor Red
        exit $exitCode
    }
    exit 0
} finally {
    Invoke-Cleanup
}
