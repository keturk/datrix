#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language domain-universe closure and stance-completeness gate.

.DESCRIPTION
 Proves two properties for every registered `datrix.languages` plugin, over
 the full shared domain universe:

 1. Domain-universe closure -- the union of every registered language's
    COMPILED GenDSL IR domain ids equals the shared registry
    (`SHARED_CONTEXT_TYPES`) exactly. A domain id some language's compiled
    IR declares but the registry omits, or a registry id no registered
    language's compiled IR declares (a dead entry), fails loud and
    short-circuits before anything downstream runs.
 2. Per-language stance completeness -- every registered language declares
    a stance (`supported` or `unsupported(reason)`) for every id in that
    closed universe, and no stance for an id outside it. A missing or
    out-of-universe stance is a fail-loud `STANCE COMPLETENESS VIOLATION`.
    This is a completeness check, never an agreement check: languages are
    free to take opposite stances on the same domain id, most commonly
    because a domain is realized elsewhere on that target (e.g. folded into
    another domain, or architecturally inapplicable to that target's
    runtime) rather than left as an unclaimed gap.

 On success, prints every registered language's full stance table (one row
 per universe id) plus a divergence report quoting each unsupported
 language's declared reason verbatim -- diagnostic only, never itself a
 failure condition.

 Derives its target language set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded language literal -- so a future `datrix-codegen-<lang>`
 package is covered automatically with no edit to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: feeds the stance-completeness comparator a complete
 synthetic table (must report zero findings), a synthetic language missing
 one universe id's stance (must be reported), and a synthetic language
 declaring an out-of-universe stance (must be reported); and feeds the
 closure comparator a synthetic matching pair (must report zero
 divergence), a synthetic compiled id absent from the registry (must be
 reported), and a synthetic dead registry entry (must be reported). Fails
 loud (exit 2) if fewer than 2 languages are registered -- a cross-language
 comparison over 0 or 1 language is vacuous.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\supported-domain-parity-gate.ps1
 Run the gate for every registered language.

.EXAMPLE
 .\supported-domain-parity-gate.ps1 -Dbg
 Run the gate with debug logging.

.EXAMPLE
 .\supported-domain-parity-gate.ps1 -SelfTest
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
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\supported_domain_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: supported_domain_parity.py not found at: $runnerScript"
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

    Write-Host "Running domain-universe closure + stance-completeness gate (all registered languages)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Supported-domain parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Supported-domain parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
