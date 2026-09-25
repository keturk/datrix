#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Field-error-path parity gate -- every registered language spells
 `request-validation` problem-body `errors[].field` paths with one
 dot-separated, `body`-prefix-free, `[n]`-array-indexed rule or declares the
 hole with a reason.

.DESCRIPTION
 A generated service's `request-validation` problem body carries an
 `errors[].field` value the UI form layer maps onto a form control. A client
 keyed on it must see the same path shape whichever language served the
 request, so the shape has one home:
 datrix_common.generation.problem_types.FIELD_ERROR_PATH_RULE (a
 dot-separated wire-name path relative to the request body root, no leading
 `body` segment, `[n]` for array elements). This gate censuses every
 registered language package's own construction technique for that shape and
 holds each language to:

   * REALIZATION -- the language's sources construct the canonical shape for
     the rule's own worked example, or the language declares the hole with a
     reason on its LanguageCapabilityDeclaration.unrealized_field_error_path.
     Neither fails by name; both is a stale declaration and fails; a
     divergent construction (a literal `body` prefix, or an array index not
     spelled `[n]`) fails naming the found and expected spelling.

 Language set from the installed datrix.languages entry points at runtime;
 declarations read from the packages -- never a table here. Runs a built-in
 non-vacuity self-test on every invocation.

 Repo-level validation script (per the datrix showcase boundary -- no pytest
 suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (per-language census detail).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real census.

.EXAMPLE
 .\field-error-path-parity-gate.ps1

.EXAMPLE
 .\field-error-path-parity-gate.ps1 -SelfTest
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
$runnerScript = Join-Path $libraryDir "test\field_error_path_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: field_error_path_parity.py not found at: $runnerScript"
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

    Write-Host "Running field-error-path parity gate (every registered language)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Field-error-path parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Field-error-path parity gate passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
