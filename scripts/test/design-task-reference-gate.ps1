#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if a committed artifact cites a design document or a task file.

.DESCRIPTION
 Design documents (design/) and task files (.tasks/) are gitignored and are
 developed on more than one machine, so their numbering collides: two different
 044-* documents can exist, and neither is present after a clone. A reference to
 one from anything that IS committed is a dangling pointer -- it resolves to
 nothing, or to a different artifact elsewhere.

 This gate scans the committed trees for the SHAPE of such a reference
 (task-NN-MM, design/NNN-slug, "design doc NNN", .tasks/phase-NN) and fails on
 any hit. Design and task files referencing each other are exempt and their
 trees are skipped -- that is gitignored orchestration machinery.

 The non-vacuity self-test runs on EVERY invocation before the real scan, so a
 green result can never mean "the detector was broken". Use -SelfTest to run
 only that leg.

.PARAMETER Roots
 Comma-separated directories to scan. When omitted, scans the committed trees:
 datrix/scripts, datrix/docs, datrix-common/src, datrix-common/docs, and
 datrix-codegen-common/src.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.EXAMPLE
 .\design-task-reference-gate.ps1
 Scan every committed tree.

.EXAMPLE
 .\design-task-reference-gate.ps1 -Roots D:/datrix/datrix/scripts/config
 Scan a single tree.

.EXAMPLE
 .\design-task-reference-gate.ps1 -SelfTest
 Prove the detector fires on a planted reference and stays quiet without one.
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
$runnerScript = Join-Path $libraryDir "test\design_task_references.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: design_task_references.py not found at: $runnerScript"
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
                   elseif ([string]::IsNullOrWhiteSpace($Roots)) { "all committed trees" }
                   else { $Roots }
    Write-Host "Running design/task reference check for: $targetLabel" -ForegroundColor Cyan

    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Design/task reference check failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Design/task reference check passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
