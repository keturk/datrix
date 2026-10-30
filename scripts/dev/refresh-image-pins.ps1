#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Rewrite every package's container image pin table from its registry.

.DESCRIPTION
 The behaviour is datrix_scripts.dev.refresh_image_pins. Every package that chooses container
 images for a generated project ships image_pins.json beside its top module: each <name>:<tag>
 reference it names, mapped to the digest of that tag's multi-platform index. This script is
 the only writer of those tables: it resolves every reference with
 `docker buildx imagetools inspect` and rewrites each table sorted by reference, so a tag moved
 upstream shows as a table diff in review. -Package limits the run to one package's table;
 -Add puts new references into that table first.
 It is the only network step of image pinning; no framework test runs it.

 A reference that does not resolve fails the run and no table is written. A registry's
 rate-limit answer is retried with a growing wait.

 Exit codes: 0 = every table rewritten, 1 = a reference did not resolve, 2 = usage error.

.PARAMETER Package
 Refresh only this package directory's table (for example datrix-codegen-docker); -Add extends it.

.PARAMETER Add
 '<name>:<tag>' references to add to -Package's table (comma-separated or repeated).

.PARAMETER SelfTest
 Run only the module's self-test: planted tables are rewritten, each refusal fires, and the
 wrapper seam holds.

.EXAMPLE
 .\dev\refresh-image-pins.ps1
 Re-resolve every reference of every table.

.EXAMPLE
 .\dev\refresh-image-pins.ps1 -Package datrix-codegen-docker -Add redis:7
 Pin a new image the docker generator names.
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(ParameterSetName = "Run")][string]$Package,
 [Parameter(ParameterSetName = "Run")][string[]]$Add,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.refresh_image_pins" -Parameters $PSBoundParameters
exit $LASTEXITCODE
