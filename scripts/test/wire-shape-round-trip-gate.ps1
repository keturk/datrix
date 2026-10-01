#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Wire-shape round-trip gate: the emitted browser client, run against a live backend.

.DESCRIPTION
 Generates BOTH a backend service and a browser client for the adopted ecommerce
 fixture application, boots the backend with `docker compose up --build --wait`,
 invokes every generated client method against it through a Node harness that
 executes the emitted client classes as shipped, and compares every response body
 against the interface the client generator emitted for it.

 This is the only check in the frontend-client program that exercises the emitted
 client against a RUNNING backend instead of reasoning about either artifact in
 isolation -- which is what makes it the one that catches a response field
 transcribed in the wrong case, or a query parameter cased against the wrong rule,
 at the source.

 It lives here, as a repo-level script rather than inside a renderer package's own
 test suite, because it asserts on the COMBINED output of two generator packages --
 a backend language package's service and the browser-client renderer's tree --
 which the repository's boundary rules forbid inside any single package. Only its
 home differs from the design that asked for it; its content does not.

 Derives its BACKEND target set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime -- never a
 hardcoded language literal. A backend that cannot be generated or booted is
 reported as SKIPPED by name and with its reason; the target set is never narrowed
 in silence.

 Also compares the backends against EACH OTHER (the "cross-language" comparison,
 reported under that label so it reads apart from the per-backend one): for every
 route, what each booted backend answered is compared against what every other
 booted backend answered -- status, media type, body shape and the casing of every
 field -- because two languages must answer the same route identically on the
 wire, and a disagreement is invisible to a check that compares each backend only
 against its own client interface. It issues no extra request: the one call the
 harness already makes per (backend, route) also records what arrived on the wire,
 through the same request pacer, bearer token and resolved base URL, so the cost
 stays one call per backend and route however many backends there are. A response
 VALUE never leaves the harness -- a body is reduced to its shape the moment it is
 captured -- so a mismatch names the JSON path and the two kinds, spellings,
 statuses or media types, and nothing else. With fewer than two booted backends, or
 no route answered by two of them, nothing was compared and the gate fails.

 Runs a non-vacuity self-test on every invocation, before trusting any real run:
 the shared response-shape comparator is driven over a synthetic matching payload
 (must report parsed), the same payload against an interface whose one property has
 been re-spelled in a different case (must report unparsed, naming that property),
 and against one declaring the wrong value kind (must report unparsed, naming that
 property). The same self-test plants responses for the cross-language comparison
 (agreeing responses must report nothing; a field re-spelled in another casing, a
 different value kind, a missing property, a different status, media type or route
 must each report exactly that, naming the path and both sides; a planted secret
 must appear in no report or log line; one captured call per backend and route),
 and drives the harness's wire capture through a real HttpClient against a
 throwaway loopback server, and its generated-client reader over a planted client
 (a method with request arguments, one with none and one with defaulted arguments
 must all be read; a method of any other shape must be refused by name). None of
 this needs Docker.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the non-vacuity self-test (comparator, cross-language comparison, wire
 capture) and skip the real generate-boot-call-compare run.

.PARAMETER ReuseGenerated
 Boot and exercise the tree a previous run already generated instead of
 regenerating it. This is what makes the gate's own negative proof possible: a
 mis-cased field planted into an emitted interface survives to the run that must
 catch it, where a fresh generation would overwrite the plant first.

.EXAMPLE
 .\wire-shape-round-trip-gate.ps1
 Run the gate for every registered backend language.

.EXAMPLE
 .\wire-shape-round-trip-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\wire-shape-round-trip-gate.ps1 -ReuseGenerated
 Re-run the full gate over the already-generated tree.
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
$runnerScript = Join-Path $libraryDir "test\wire_shape_round_trip.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: wire_shape_round_trip.py not found at: $runnerScript"
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

    Write-Host "Running wire-shape round-trip gate (adopted fixture, every registered backend)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Wire-shape round-trip gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Wire-shape round-trip gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
