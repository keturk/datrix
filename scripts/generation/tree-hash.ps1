#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Snapshot the SHA-256 of every file under generated trees, and diff two snapshots.

.DESCRIPTION
 Wraps generation\lib\tree_hash.py. The check behind "this refactor changes no output":
 snapshot the generated tree, make the change, regenerate, snapshot again, diff. Keys are
 <root name>/<relative path>, so two checkouts or two output directories compare file by
 file. .git, node_modules, __pycache__ and tool caches are skipped.

 compare-generated.ps1 compares features by content against .generated_saved; this
 compares bytes, file by file.

 Exit codes: -Snapshot 0; -Diff 0 = identical, 1 = files added/removed/changed (listed),
 2 = bad input.

.PARAMETER Snapshot
 Write a manifest of -Root to -Manifest.

.PARAMETER Diff
 Compare -Before with -After.

.PARAMETER Manifest
 Manifest file to write (keep it outside the package repos, e.g. D:\datrix\.tmp\before.json).

.PARAMETER Root
 Trees to hash (one or more; their directory names must differ).

.PARAMETER Before
 Earlier manifest.

.PARAMETER After
 Later manifest.

.PARAMETER Limit
 Paths listed per diff section (0 = all). Default: 50.

.EXAMPLE
 .\generation\tree-hash.ps1 -Snapshot -Manifest D:\datrix\.tmp\before.json -Root D:\datrix\.generated\python\docker-compose\local\03-domains\ecommerce
 Hash the generated ecommerce tree before a refactor.

.EXAMPLE
 .\generation\tree-hash.ps1 -Diff -Before D:\datrix\.tmp\before.json -After D:\datrix\.tmp\after.json
 List every file the refactor added, removed or changed.
#>

[CmdletBinding(DefaultParameterSetName = "Snapshot")]
param(
    [Parameter(ParameterSetName = "Snapshot", Mandatory = $true)]
    [switch]$Snapshot,
    [Parameter(ParameterSetName = "Snapshot", Mandatory = $true)]
    [string]$Manifest,
    [Parameter(ParameterSetName = "Snapshot", Mandatory = $true)]
    [string[]]$Root,

    [Parameter(ParameterSetName = "Diff", Mandatory = $true)]
    [switch]$Diff,
    [Parameter(ParameterSetName = "Diff", Mandatory = $true)]
    [string]$Before,
    [Parameter(ParameterSetName = "Diff", Mandatory = $true)]
    [string]$After,
    [Parameter(ParameterSetName = "Diff")]
    [ValidateRange(0, [int]::MaxValue)]
    [int]$Limit = 50
)

$ErrorActionPreference = "Stop"

# `powershell -File` passes "a,b" as one string; accept both that and a real array.
if ($Root) { $Root = @($Root | ForEach-Object { $_ -split ',' } | ForEach-Object { $_.Trim() } | Where-Object { $_ }) }

Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = if ($Snapshot) { @("snapshot", $Manifest) + $Root } else { @("diff", $Before, $After, "--limit", "$Limit") }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\tree_hash.py") -Arguments $pythonArgs)
