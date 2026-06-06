#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Dead-code report: never referenced vs only referenced by tests (two-pass Vulture).

.DESCRIPTION
 Ensures the datrix venv is active and runs dead_code_report.py with two-pass Vulture.
Reports dead code in src/ only, classified as "never referenced" or "only referenced by tests".

.PARAMETER Projects
 One or more project names or folder paths (e.g. datrix-common, .\datrix-codegen-aws\). If omitted, uses the default 11 packages.

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

.PARAMETER LlmReview
 Add an advisory local LLM review for the top deterministic findings.

.PARAMETER LlmLimit
 Maximum findings to include in the advisory LLM review. Default: 30.

.PARAMETER OllamaUrl
 Ollama server URL for advisory LLM review.

.PARAMETER LlmModel
 Local LLM model for advisory review.

.PARAMETER LlmTimeout
 Ollama request timeout in seconds for advisory review.

.PARAMETER LlmNumPredict
 Ollama max generated tokens for advisory review.

.PARAMETER LlmTemperature
 Ollama temperature for advisory review.

.PARAMETER LlmKeepAlive
 Ollama keep_alive value for advisory review.

.PARAMETER Quiet
 Only write to -OutputPath (if set); do not print to console.

.EXAMPLE
  .\dead-code-report.ps1
  .\dead-code-report.ps1 -All -Output json | Out-File report.json
  .\dead-code-report.ps1 datrix-common .\datrix-language\ -MinConfidence 100 -OutputPath dead-code.md
  .\dead-code-report.ps1 -All -Raw
  .\dead-code-report.ps1 datrix-cli -LlmReview -LlmLimit 20
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
 [switch]$LlmReview,
 [int]$LlmLimit = 30,
 [string]$OllamaUrl = "http://10.94.0.100:11434",
 [string]$LlmModel = "qwen3-coder:30b-ctx32k",
 [int]$LlmTimeout = 180,
 [int]$LlmNumPredict = 4096,
 [double]$LlmTemperature = 0.1,
 [string]$LlmKeepAlive = "10m",
 [switch]$Quiet
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
$venvUtilsScript = Join-Path $commonDir "venv.ps1"
$workspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path
$datrixCommon = Join-Path $workspaceRoot "datrix"
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
 $normalizedProjects = @()
 if ($Projects.Count -gt 0) {
  $normalizedProjects = ($Projects | ForEach-Object { ConvertTo-DatrixProjectName -ProjectInput $_ }) |
   Where-Object { $_ -ne "datrix" } |
   Select-Object -Unique

  if ($normalizedProjects.Count -eq 0) {
   Write-Error "No valid projects selected. Pass one or more datrix-* package names or paths (excluding 'datrix')."
   exit 1
  }
 }

 $pyArgs = @(
  "--workspace-root", $workspaceRoot,
  "--min-confidence", $MinConfidence,
  "--output", $Output
 )
 if ($All) { $pyArgs += "--all" }
 elseif ($normalizedProjects.Count -gt 0) {
  $pyArgs += "--projects"
  $pyArgs += $normalizedProjects
 }
 if ($VerboseOutput) { $pyArgs += "--verbose" }
 if ($Raw) { $pyArgs += "--raw" }
 if ($LlmReview) {
  $pyArgs += @(
   "--llm-review",
   "--llm-limit", $LlmLimit,
   "--ollama-url", $OllamaUrl,
   "--llm-model", $LlmModel,
   "--llm-timeout", $LlmTimeout,
   "--llm-num-predict", $LlmNumPredict,
   "--llm-temperature", $LlmTemperature,
   "--llm-keep-alive", $LlmKeepAlive
  )
 }

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

