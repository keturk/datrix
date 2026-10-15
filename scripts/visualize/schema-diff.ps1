<#
.SYNOPSIS
    Compare two .dtrx files and report schema changes.

.DESCRIPTION
    Parses two .dtrx source files, produces a structural diff, and outputs
    a report in Markdown or JSON format. Identifies breaking vs non-breaking changes.

.PARAMETER Before
    Path to the earlier .dtrx file (baseline).

.PARAMETER After
    Path to the later .dtrx file (comparison target).

.PARAMETER Format
    Output format: markdown or json (default: markdown).

.PARAMETER Output
    Output file path. If omitted, writes to stdout.

.PARAMETER Dbg
    Enable debug logging.

.EXAMPLE
    .\schema-diff.ps1 v1\system.dtrx v2\system.dtrx
    Compare two versions and print Markdown diff to stdout.

.EXAMPLE
    .\schema-diff.ps1 v1\system.dtrx v2\system.dtrx -Format json -Output changes.json
    Compare and write JSON diff to a file.
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0, Mandatory = $true)]
    [string]$Before,

    [Parameter(Position = 1, Mandatory = $true)]
    [string]$After,

    [ValidateSet("markdown", "json")]
    [string]$Format = "markdown",

    [string]$Output,
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pyArgs = @("--before", $Before, "--after", $After)
if ($Format -ne "markdown") { $pyArgs += @("--format", $Format) }
if ($Output) { $pyArgs += @("--output", $Output) }
if ($Dbg) { $pyArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\schema_diff.py") -Arguments $pyArgs)
