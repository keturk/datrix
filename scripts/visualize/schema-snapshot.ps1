<#
.SYNOPSIS
    Save .dtrx Application as a JSON snapshot for future diffs.

.DESCRIPTION
    Parses .dtrx files and serializes the Application model to JSON.
    Snapshots can be compared with schema-diff.ps1 to detect changes.
    Supports single-file and batch modes.

.PARAMETER Source
    Path to .dtrx file or directory (single mode).

.PARAMETER All
    Snapshot all projects from test-projects.json.

.PARAMETER Domains
    Domain examples only.

.PARAMETER TestSet
    Named test set from test-projects.json (default: all).

.PARAMETER Output
    Explicit output file path (overrides default location).

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\schema-snapshot.ps1 examples\02-domains\ecommerce\system.dtrx
    Create a snapshot for the ecommerce example.

.EXAMPLE
    .\schema-snapshot.ps1 -All
    Create snapshots for all projects.

#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Source,

    [switch]$All,
    [switch]$Domains,
    [string]$TestSet = "all",

    [string]$Output,
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @()
if ($Source) { $pyArgs += @("--source", $Source) }
if ($All) { $pyArgs += "--all" }
if ($Domains) { $pyArgs += "--domains" }
if ($TestSet -ne "all") { $pyArgs += @("--test-set", $TestSet) }
if ($Output) { $pyArgs += @("--output", $Output) }
if ($Dbg) { $pyArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\schema_snapshot.py") -Arguments $pyArgs)
