#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Zero-environment runtime census gate -- every registered language is held to
 the zero_environment_runtime posture it declares.

.DESCRIPTION
 The zero-environment runtime architecture bakes every deployment-static value
 into literal constants at generation time; the running service consults no
 environment variable. Its realization is per language, so each language
 plugin declares its posture on its LanguageCapabilityDeclaration
 (zero_environment_runtime: realized or not, the regular expressions that
 spell an environment read in its own templates, and a written reason when
 unrealized). This gate censuses every .j2 template under each registered
 language package's src/ tree against that language's declared idioms and:

   * a language declaring the contract REALIZED may carry environment reads
     only as reviewed exemptions with a written reason in
     scripts/config/zero-environment-runtime-baseline.json -- an unlisted read
     and a stale entry are both violations;
   * a language declaring the contract UNREALIZED carries a decrease-only
     pinned count that may never rise;
   * a registered language that declares nothing fails, named.

 Language set from the installed datrix.languages entry points at runtime;
 idioms from each language's own declaration -- never a table here. Runs a
 built-in non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (lists every environment-reading template).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real census.

.PARAMETER UpdateBaseline
 Re-pin every unrealized language's count to its live census (the only writer
 of pinned_count values). Realized languages' exemption lists are hand-authored
 and left untouched.

.EXAMPLE
 .\zero-environment-runtime-gate.ps1

.EXAMPLE
 .\zero-environment-runtime-gate.ps1 -UpdateBaseline
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$UpdateBaseline
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\zero_environment_runtime_gate.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: zero_environment_runtime_gate.py not found at: $runnerScript"
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
    if ($UpdateBaseline) {
        $pythonArgs += "--update-baseline"
    }

    Write-Host "Running zero-environment runtime census gate (every registered language)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Zero-environment runtime census gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Zero-environment runtime census gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
