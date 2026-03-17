#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Dead-code report: never referenced vs only referenced by tests (two-pass Vulture).

.DESCRIPTION
 Ensures the datrix venv is active and runs dead_code_report.py with two-pass Vulture.
Reports dead code in src/ only, classified as "never referenced" or "only referenced by tests".

.PARAMETER Projects
 One or more project names (e.g. datrix-common, datrix-language). If omitted, uses the default 11 packages.

.PARAMETER All
 Scan all datrix-* projects (except datrix). Overrides default project list.

.PARAMETER MinConfidence
 Vulture min confidence 60-100. Default: 60 (include functions/classes).

.PARAMETER Output
 Report format: text or json. Default: text.

.PARAMETER OutputPath
 Optional file path to write the report (stdout is still printed unless -Quiet).

.PARAMETER VerboseOutput
 Verbose progress to stderr.

.PARAMETER Raw
 Disable false-positive filters (show all Vulture findings).

.PARAMETER Quiet
 Only write to -OutputPath (if set); do not print to console.

.EXAMPLE
 .\dead_code_report.ps1
 .\dead_code_report.ps1 -All -Output json | Out-File report.json
 .\dead_code_report.ps1 datrix-common datrix-language -MinConfidence 100 -OutputPath dead-code.md
 .\dead_code_report.ps1 -All -Raw
#>

[CmdletBinding()]
param(
 [Parameter(Position = 0, ValueFromRemainingArguments = $true)]
 [string[]]$Projects,

 [switch]$All,
 [int]$MinConfidence = 60,
 [ValidateSet("text", "json")]
 [string]$Output = "text",
 [string]$OutputPath,
 [switch]$VerboseOutput,
 [switch]$Raw,
 [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$datrixCommon = Split-Path -Parent (Split-Path -Parent $scriptDir)
$datrixRoot = Split-Path -Parent $datrixCommon

$commonDir = Join-Path $datrixCommon "scripts\common"
$venvUtilsScript = Join-Path $commonDir "venv.ps1"
$deadCodeReportPy = Join-Path $datrixCommon "scripts\library\metrics\dead_code_report.py"

if (-not (Test-Path $venvUtilsScript)) {
 Write-Error "Error: Common venv utilities not found at: $venvUtilsScript"
 exit 1
}
. $venvUtilsScript

if (-not (Test-Path $deadCodeReportPy)) {
 Write-Error "Error: dead_code_report.py not found at: $deadCodeReportPy"
 exit 1
}

function Invoke-Cleanup {
 Disable-DatrixVenv
}
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null
trap {
 Invoke-Cleanup
 exit 130
}

if (-not (Ensure-DatrixVenv)) {
 Write-Error "Failed to ensure venv"
 exit 1
}

try {
 $pyArgs = @(
  "--workspace-root", $datrixRoot,
  "--min-confidence", $MinConfidence,
  "--output", $Output
 )
 if ($All) { $pyArgs += "--all" }
 elseif ($Projects.Count -gt 0) {
  $pyArgs += "--projects"
  $pyArgs += $Projects
 }
 if ($VerboseOutput) { $pyArgs += "--verbose" }
 if ($Raw) { $pyArgs += "--raw" }

 if ($OutputPath) {
  & python $deadCodeReportPy @pyArgs | Set-Content -Path $OutputPath -Encoding utf8
  if (-not $Quiet) {
   Get-Content -Path $OutputPath
  }
 } else {
  & python $deadCodeReportPy @pyArgs
 }

 exit $LASTEXITCODE
} finally {
 Invoke-Cleanup
}
