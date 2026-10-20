#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Regenerate the builtin seed reference datasets from their authoritative sources.

.DESCRIPTION
 The behaviour is datrix_scripts.generation.refresh_seed_datasets. Downloads each pinned (or
 hash-recorded) source, applies the documented transform and writes the seven dataset files,
 each carrying its provenance and licence, into
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

.PARAMETER SelfTest
 Run only the module's self-test, which needs no network and writes nothing: a planted cache
 entry is served and transformed, the committed datasets match SEED_DATASETS, and the wrapper
 seam holds.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run")][string]$CacheDir,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.generation.refresh_seed_datasets" -Parameters $PSBoundParameters
exit $LASTEXITCODE
