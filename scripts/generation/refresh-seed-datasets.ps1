#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Regenerate the builtin seed reference datasets from their authoritative sources.

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

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($CacheDir) { $pythonArgs += @("--cache-dir", $CacheDir) }
$env:PYTHONIOENCODING = "utf-8"

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\refresh_seed_datasets.py") -Arguments $pythonArgs)
