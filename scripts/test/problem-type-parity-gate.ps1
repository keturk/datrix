#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Problem-type parity gate -- every registered language answers errors with
 RFC 7807 type URNs from datrix-common's registry and realizes every
 framework family or declares the hole with a reason.

.DESCRIPTION
 A generated service's error body carries a `type` member naming the error
 class; a client keyed on it must see one vocabulary whichever language
 served the request. The vocabulary has one home,
 datrix_common.generation.problem_types (urn:datrix:error:<slug>). This gate
 censuses the .py and .j2 sources under every registered language package
 for urn:datrix:error: literals and holds each language to:

   * SPELLING -- every literal slug is a registered family (a private slug
     has no exemption path: register it or spell the registered one);
   * REALIZATION -- every registered family is spelled by the language or
     declared unrealized with a reason on the language's
     LanguageCapabilityDeclaration.unrealized_problem_types. Neither fails
     by name; both is a stale declaration and fails; a family no language
     spells is a dead registry entry and fails.

 Language set from the installed datrix.languages entry points at runtime;
 registry and declarations read from the packages -- never a table here.
 Runs a built-in non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (per-language spelling counts).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real census.

.EXAMPLE
 .\problem-type-parity-gate.ps1

.EXAMPLE
 .\problem-type-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\problem_type_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: problem_type_parity.py not found at: $runnerScript"
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

    Write-Host "Running problem-type parity gate (every registered language)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Problem-type parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Problem-type parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
