#!/usr/bin/env pwsh
<#
.SYNOPSIS
 API-key identity round-trip gate: revocation, tenant scoping, exact concurrent
 rate limiting, bounded lastUsedAt writes, and cross-language parity, against a
 live backend.

.DESCRIPTION
 Generates the key-bearing ecommerce fixture application (its `customerKeys`
 API-key provider) and a tenant-scoped companion fixture for every registered
 backend language, boots each with real Postgres and Redis through
 `docker compose up -d --build --wait`, issues real keys through the generated
 issuance endpoint, and proves against the running stack that:

 - a key is refused on the very next request once its stored row is deactivated;
 - a request tenant differing from the key's stored tenant is refused 403, and a
   matching or absent one is admitted;
 - N truly concurrent requests on a key limited to L admit exactly min(N, L);
 - K verifications inside one lastUsedAt resolution window write the key row once;
 - every backend renders the same outcome vector for every probe above.

 It lives here, as a repo-level script rather than inside a package's own test
 suite, because it asserts on the COMBINED output of several generator packages,
 which the repository's boundary rules forbid inside any single package.

 Derives its backend target set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime -- never a
 hardcoded language literal -- and refuses to run with fewer than two, because
 cross-language parity is vacuous with one. Every stack it boots is torn down,
 volumes included, whatever happens, and the run fails if any container is left.

 Runs a non-vacuity self-test on every invocation, before any container is
 started: a success answer for a revoked (inactive) key row must be rejected by
 the 'ok' outcome classifier, a burst admitting one request over its limit must
 be rejected, and K verifications each writing the row must be rejected.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip generation and boot.

.PARAMETER ReuseGenerated
 Boot and probe the trees a previous run already generated instead of
 regenerating them.

.EXAMPLE
 .\api-key-identity-round-trip-gate.ps1
 Run the gate for every registered backend language.

.EXAMPLE
 .\api-key-identity-round-trip-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\api-key-identity-round-trip-gate.ps1 -ReuseGenerated
 Re-run the full gate over the already-generated trees.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ReuseGenerated
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\api_key_identity_round_trip.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: api_key_identity_round_trip.py not found at: $runnerScript"
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
    if ($ReuseGenerated) {
        $pythonArgs += "--reuse-generated"
    }

    Write-Host "Running API-key identity round-trip gate (every registered backend)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "API-key identity round-trip gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "API-key identity round-trip gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
