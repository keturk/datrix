#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Generate documentation fragments from source code.

.DESCRIPTION
    The behaviour is datrix_scripts.dev.generate_doc_fragments. Extracts documentation from
    source-of-truth code locations and writes markdown fragment files to datrix/docs/generated/.

    Two fragment types are supported:
    - semantic-pipeline: Ordered list of semantic analyzer phases
    - cli-help: Full `datrix generate --help` output

    Supports -Check mode for verification.

.PARAMETER Fragment
    Which fragment to generate: semantic-pipeline, cli-help, or all (default: all).

.PARAMETER Check
    Verify mode: check that existing fragments are up-to-date.
    Exits with non-zero status if any fragment is stale.

.PARAMETER Dbg
    Print detailed output during generation.

.PARAMETER SelfTest
    Run only the module's self-test: check mode reports OK, STALE and missing fragments, and the
    wrapper seam holds.

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
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position = 0, ParameterSetName = "Run")][ValidateSet("all", "semantic-pipeline", "cli-help")][string]$Fragment = "all",
 [Parameter(ParameterSetName = "Run")][switch]$Check,
 [switch]$Dbg,
 [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")][switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.dev.generate_doc_fragments" -Parameters $PSBoundParameters
exit $LASTEXITCODE
