#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Web security header parity gate -- every registered platform realizing
 static web hosting emits datrix-common's one declared security-header set
 and realizes every header family for its own topology, or the CSP contains
 no unsafe-inline/unsafe-eval token.

.DESCRIPTION
 A generated static site's security headers -- Content-Security-Policy,
 Strict-Transport-Security, X-Content-Type-Options, Referrer-Policy,
 Permissions-Policy -- have one home:
 datrix_common.generation.web_security_headers.build_web_security_headers.
 Every platform that realizes static_web_hosting (docker/local's loopback
 nginx container, AWS's CloudFront response-headers policy, Azure's Static
 Web Apps staticwebapp.config.json) consumes it, but none spells a header
 name literally in its own source -- each threads the shared builder's
 output straight into its own rendering primitive. This gate DRIVES each
 platform's real generation composition for one shared fixture (app, web
 target, environment) and parses the EMITTED artifact structurally (nginx
 add_header directives, the CloudFront response-headers policy's CDK IR, the
 parsed staticwebapp.config.json) to hold each platform to:

   * REALIZATION -- every header family the platform's own topology expects
     (read from its PlatformCapabilityDeclaration.static_web_hosting.origin;
     a loopback platform correctly omits Strict-Transport-Security) is
     realized in the emitted artifact. There is no declared-hole escape for
     this gate -- a platform realizing static_web_hosting must realize the
     full topology-appropriate set, always;
   * CSP SAFETY -- no emitted Content-Security-Policy value contains
     unsafe-inline or unsafe-eval, independent of family completeness.

 Platform set from the installed datrix.platforms entry points at runtime;
 the declared header set read from datrix-common at runtime -- never a
 table here. Runs a built-in non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (per-platform census detail).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real census.

.EXAMPLE
 .\web-security-header-parity-gate.ps1

.EXAMPLE
 .\web-security-header-parity-gate.ps1 -SelfTest
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
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\web_security_header_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: web_security_header_parity.py not found at: $runnerScript"
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

    Write-Host "Running web security header parity gate (every registered platform)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Web security header parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Web security header parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
