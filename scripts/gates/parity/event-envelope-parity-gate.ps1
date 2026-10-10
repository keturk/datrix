#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language pubsub event-envelope parity gate.

.DESCRIPTION
 Proves every registered `datrix.languages` plugin puts ONE event envelope on the
 wire and reads the same one back, so a topic with producers and consumers in
 different languages delivers every event. Generates the shared pubsub example
 (datrix/examples/02-features/02-service-architecture/pubsub/) once per
 registered language and reads each language's own producers and consumers
 through its `LanguageConformanceProbes.event_envelopes`:

 - every published envelope carries exactly the declared keys
   (`datrix_codegen_kernel.generation.event_envelope`);
 - every payload carries exactly its event parameters' wire names;
 - every key a consumer reads is a key the producers write;
 - every event two languages publish has one payload key set.

 Derives its target language set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime -- never
 a hardcoded language literal.

 Runs a built-in non-vacuity self-test on every invocation, before trusting any
 real comparison: a conformant fixture census (no violation), a snake_case
 envelope (producer and consumer both reported), a snake_case payload, two
 languages disagreeing on a payload, and an empty census (all reported). Fails
 loud (exit 2) if fewer than 2 languages are registered.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip real generation.

.EXAMPLE
 .\event-envelope-parity-gate.ps1
 Run the gate for every registered language.

.EXAMPLE
 .\event-envelope-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $scriptDir "lib\event_envelope_parity.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: event_envelope_parity.py not found at: $runnerScript"
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
    if ($Dbg) {
        $pythonArgs += "--debug"
    }
    if ($SelfTest) {
        $pythonArgs += "--self-test"
    }

    Write-Host "Running pubsub event-envelope parity gate (all registered languages)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Event-envelope parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Event-envelope parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
