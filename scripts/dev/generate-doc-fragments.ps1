#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generate documentation fragments from source code.

.DESCRIPTION
    Extracts documentation from source-of-truth code locations and writes
    markdown fragment files to datrix/docs/generated/.

    Two fragment types are supported:
    - semantic-pipeline: Ordered list of semantic analyzer phases
    - cli-help: Full `datrix generate --help` output

    Supports --Check mode for CI verification.

.PARAMETER Fragment
    Which fragment to generate: semantic-pipeline, cli-help, or all (default: all).

.PARAMETER Check
    Verify mode: check that existing fragments are up-to-date.
    Exits with non-zero status if any fragment is stale.

.PARAMETER Dbg
    Print detailed output during generation.

.EXAMPLE
    .\generate-doc-fragments.ps1
    # Generate all fragments

.EXAMPLE
    .\generate-doc-fragments.ps1 -Fragment semantic-pipeline
    # Generate only the semantic pipeline fragment

.EXAMPLE
    .\generate-doc-fragments.ps1 -Check
    # Verify all fragments are up-to-date
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet("all", "semantic-pipeline", "cli-help")]
    [string]$Fragment = "all",

    [switch]$Check,

    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @()
if ($Fragment -ne "all") { $pyArgs += @("--fragment", $Fragment) }
if ($Check) { $pyArgs += "--check" }
if ($Dbg) { $pyArgs += "--verbose" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\generate_doc_fragments.py") -Arguments $pyArgs)
