#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if a `from <datrix module> import <name>` names something that does not exist.

.DESCRIPTION
 A half-completed rename leaves a module importing one name and defining
 another. When the import runs, the first test that touches the module raises
 ImportError and the suite goes red. When it sits inside `if TYPE_CHECKING:`,
 nothing happens at all -- the block never executes, every package still
 imports cleanly, and this repository runs no standalone type-checker by
 policy. Every annotation written against that name is then meaningless, and
 nothing will ever say so.

 This gate resolves every `from <module> import <name>` whose module belongs to
 a Datrix package against whether the name actually exists there, by three
 routes in order: a module-level binding in that module's own source (AST,
 including its own TYPE_CHECKING block), a submodule of that module, and
 finally a runtime attribute after importing it. Runtime imports are checked
 alongside TYPE_CHECKING ones because it costs nothing once the resolver
 exists.

 Deliberate negative-existence assertions -- an import inside
 `pytest.raises(ImportError)` or `try/except ImportError`, written to prove a
 deleted symbol is gone -- are excluded and counted, never reported.

 The terminal state is zero. There is no baseline and no ratchet: a name that
 resolves by none of the three routes is a defect in the importing module.

 The non-vacuity self-test runs on EVERY invocation before the real scan, so a
 green result can never mean "the resolver was broken". Use -SelfTest to run
 only that leg.

.PARAMETER Roots
 Comma-separated directories to scan. When omitted, scans every `src/` and
 `tests/` tree of every `datrix*` package repo plus the showcase repo's
 `scripts/` tree, derived from what is on disk.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.EXAMPLE
 .\import-name-existence-gate.ps1
 Scan every Datrix package tree.

.EXAMPLE
 .\import-name-existence-gate.ps1 -Roots D:/datrix/datrix-common/src
 Scan a single tree.

.EXAMPLE
 .\import-name-existence-gate.ps1 -SelfTest
 Prove the resolver flags planted dead names and leaves every documented
 false-positive family alone.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Roots = "",

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\import_name_existence.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: import_name_existence.py not found at: $runnerScript"
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
    if ($SelfTest) {
        $pythonArgs += "--self-test"
    }
    elseif (-not [string]::IsNullOrWhiteSpace($Roots)) {
        foreach ($item in $Roots.Split(",")) {
            $trimmed = $item.Trim()
            if (-not [string]::IsNullOrWhiteSpace($trimmed)) {
                $pythonArgs += $trimmed
            }
        }
    }

    $targetLabel = if ($SelfTest) { "self-test only" }
                   elseif ([string]::IsNullOrWhiteSpace($Roots)) { "every datrix package tree" }
                   else { $Roots }
    Write-Host "Running import-name existence check for: $targetLabel" -ForegroundColor Cyan

    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Import-name existence check failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Import-name existence check passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
