#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Regenerate the builtin SeedDSL reference datasets from their authoritative sources.

.DESCRIPTION
 Downloads each pinned (or hash-recorded) source, applies the documented transform and
 writes the seven dataset files, each carrying its provenance and licence, into
 datrix-codegen-kernel/src/datrix_codegen_kernel/seed_data. Afterwards it compares every file
 with SEED_DATASETS in datrix_common and exits 1 while they differ, printing the row counts
 and maxima the schema must carry.

 It is a script, not a test, because it needs the network.

 Exit codes:
   0 = files regenerated and equal to SEED_DATASETS
   1 = files regenerated; SEED_DATASETS differs (update its constants) or a source failed

.PARAMETER CacheDir
 Directory caching downloaded sources by URL (default: .tmp\seed-source-cache in the workspace).
 Delete it to force a fresh download.
#>
[CmdletBinding()]
param(
    [Parameter()]
    [string]$CacheDir
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "refresh_seed_datasets.py"
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: refresh_seed_datasets.py not found at: $pythonScript"
    exit 2
}

try {
    if (-not (Ensure-DatrixVenv)) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }
    $pythonExe = Join-Path (Get-DatrixVenvPath) "Scripts\python.exe"
    $pythonArgs = @($pythonScript)
    if ($CacheDir) { $pythonArgs += "--cache-dir"; $pythonArgs += $CacheDir }
    $env:PYTHONIOENCODING = "utf-8"
    & $pythonExe @pythonArgs
    exit $LASTEXITCODE
}
finally {
    Disable-DatrixVenv
}
