#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Framework header parity gate -- every registered language spells the
 framework-minted HTTP headers from datrix-common's registry and realizes
 every header family or declares the hole with a reason.

.DESCRIPTION
 A generated service exchanges a handful of headers Datrix itself defines
 (the trusted-caller token, the delegated-user envelope, the rate-limit
 response headers, the inbound webhook secret, the outbound webhook delivery
 headers). Each is a cross-language wire contract with one home:
 datrix_common.generation.http_headers. This gate censuses the .py and .j2
 sources under every registered language package and holds each language to:

   * SPELLING -- a header under a framework prefix (X-Datrix-, X-RateLimit-,
     X-Webhook-) is an exact registered name or a reviewed, counted entry in
     scripts/config/framework-header-exemptions.json; a retired name is a
     violation with no exemption path;
   * REALIZATION -- every registered family is realized (the exact name
     spelled, or its registry constant referenced from python) or declared
     unrealized with a reason on the language's
     LanguageCapabilityDeclaration.unrealized_framework_headers. Neither
     fails by name; both at once is a stale declaration and fails; a family
     no language realizes is a dead registry entry and fails.

 Language set from the installed datrix.languages entry points at runtime;
 registry and declarations read from the packages -- never a table here.
 Runs a built-in non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (per-language spelling and constant-reference counts).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real census.

.EXAMPLE
 .\framework-header-parity-gate.ps1

.EXAMPLE
 .\framework-header-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\framework_header_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: framework_header_parity.py not found at: $runnerScript"
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

    Write-Host "Running framework header parity gate (every registered language)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Framework header parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Framework header parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
