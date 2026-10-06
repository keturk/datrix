#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Parse test or generation logs and group failures by root cause.

.DESCRIPTION
 Reads a test output log or generation results file and groups failures by likely root
 cause. Produces a summary table suitable for driving checkpoint-based debugging sessions.

 Supports:
   - pytest output logs (from test.ps1 or test-single.ps1)
   - Generation result logs (from generate.ps1)
   - Deploy test logs (from deploy tests)

 The triage output is designed to feed directly into /fix-tests or /checkpoint-debug
 skills as input.

 Exit codes:
   0 = log parsed successfully (failures may or may not exist)
   1 = parse error or file not found
   2 = usage error

.PARAMETER LogPath
 Path to the log file to parse. Accepts:
   - .log files (generation results, deploy tests)
   - .txt files (captured pytest output)
   - Directories containing test result logs

.PARAMETER Format
 Force a specific parser. Auto-detected from file content if not specified.
 Valid: pytest, generate, deploy

.PARAMETER OutputFile
 Write triage report to a file instead of stdout. Produces Markdown.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER LlmSummary
 Append an advisory local LLM triage summary.

.PARAMETER LlmLimit
 Maximum failure groups to include in the advisory LLM summary. Default: 10.

.PARAMETER LocalMachines
 Machines to search for local model servers, in preference order. Omit to search the
 default list in common/lib/datrix_scripts/local_llm.py.

.PARAMETER LlmModel
 Models to use for advisory summary, best first. Omit to use any model already in memory.

.PARAMETER LlmTimeout
 Request timeout in seconds for advisory summary.

.PARAMETER LlmNumPredict
 Max generated tokens for advisory summary.

.PARAMETER LlmTemperature
 Sampling temperature for advisory summary.

.EXAMPLE
 .\triage-failures.ps1 "D:\datrix\.generated\.results\generate-results-20260503-172334.log"
 Parse generation log and group failures.

.EXAMPLE
 .\triage-failures.ps1 "D:\datrix\datrix-codegen-python\.test_results\test-output.log"
 Parse pytest output log.

.EXAMPLE
 .\triage-failures.ps1 "D:\datrix\.generated\.results\generate-results-20260503-172334.log" -OutputFile "D:\datrix\triage.md"
 Write triage report to a Markdown file.
#>

[CmdletBinding()]
param(
 [Parameter(Position=0, Mandatory=$true)]
 [string]$LogPath,

 [Parameter()]
 [ValidateSet("pytest", "generate", "deploy", "")]
 [string]$Format = "",

 [Parameter()]
 [string]$OutputFile = "",

 [Parameter()]
 [switch]$Dbg,

 [Parameter()]
 [switch]$LlmSummary,

 [Parameter()]
 [int]$LlmLimit = 10,

 [Parameter()]
 [string[]]$LocalMachines = @(),

 [Parameter()]
 [string[]]$LlmModel = @(),

 [Parameter()]
 [int]$LlmTimeout = 180,

 [Parameter()]
 [int]$LlmNumPredict = 4096,

 [Parameter()]
 [double]$LlmTemperature = 0.1
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "lib\triage_failures.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Check if Python script exists
if (-not (Test-Path $pythonScript)) {
 Write-Error "Error: triage_failures.py not found at: $pythonScript"
 exit 1
}

# Function to handle cleanup on exit
function Invoke-Cleanup {
 Disable-DatrixVenv
}

# Register cleanup on script exit
Register-EngineEvent PowerShell.Exiting -Action { Invoke-Cleanup } | Out-Null

# Trap Ctrl-C to ensure proper cleanup
trap {
 Write-Host ""
 Write-Warning "Interrupted by user (Ctrl-C)"
 Invoke-Cleanup
 exit 130
}

# Main execution with proper error handling
try {
 # Activate virtual environment
 $venvActivated = Ensure-DatrixVenv
 if (-not $venvActivated) {
  Write-Error "Failed to activate virtual environment"
  exit 1
 }

 # Get Python executable from venv
 $venvPath = Get-DatrixVenvPath
 $pythonExe = Join-Path $venvPath "Scripts\python.exe"

 # Build arguments for Python script
 $pythonArgs = @($pythonScript, $LogPath)
 if ($Format) { $pythonArgs += "--format"; $pythonArgs += $Format }
 if ($OutputFile) { $pythonArgs += "--output"; $pythonArgs += $OutputFile }
 if ($Dbg) { $pythonArgs += "--debug" }
 if ($LlmSummary) {
  $pythonArgs += @(
   "--llm-summary",
   "--llm-limit", $LlmLimit,
   "--llm-num-predict", $LlmNumPredict,
   "--llm-temperature", $LlmTemperature
  )
  $pythonArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
 }

 # Run the Python script
 & $pythonExe @pythonArgs
 $exitCode = $LASTEXITCODE

 exit $exitCode

} catch {
 Write-Host ""
 Write-Host "Error occurred:" -ForegroundColor Red
 Write-Host $_.Exception.Message -ForegroundColor Red
 Invoke-Cleanup
 exit 1
} finally {
 Invoke-Cleanup
}
