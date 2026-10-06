<#
.SYNOPSIS
    Compare .generated vs .generated_saved with content-level feature detection.

.DESCRIPTION
    Runs the exhaustive content-level comparison script and writes a Markdown report.
    Feature detection is by file content (same feature may be in different paths).
    Report default: <datrix_root>\generated-comparison-report.md.

.PARAMETER Current
    Current generated root (default: .generated).

.PARAMETER Saved
    Saved (old) generated root (default: .generated_saved).

.PARAMETER Report
    Output report path under datrix root (default: generated-comparison-report.md).

.PARAMETER LlmSummary
    Append advisory local LLM summary to the generated comparison report.

.PARAMETER LlmLimit
    Maximum feature/project rows to include in advisory LLM summary. Default: 40.

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
    .\compare-generated.ps1
    Compare defaults and write report to datrix_root\generated-comparison-report.md.

.EXAMPLE
    .\compare-generated.ps1 -Report my-report.md
    Write report to datrix_root\my-report.md.
#>
[CmdletBinding()]
param(
    [string]$Current = ".generated",
    [string]$Saved = ".generated_saved",
    [string]$Report = "generated-comparison-report.md",
    [switch]$LlmSummary,
    [int]$LlmLimit = 40,
    [string[]]$LocalMachines = @(),
    [string[]]$LlmModel = @(),
    [int]$LlmTimeout = 180,
    [int]$LlmNumPredict = 4096,
    [double]$LlmTemperature = 0.1
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
$pythonScript = Join-Path $scriptDir "lib\compare_generated.py"

. (Join-Path $commonDir "venv.ps1")
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force

if (-not (Test-Path $pythonScript)) {
    Write-Error "compare_generated.py not found at: $pythonScript"
    exit 1
}

$venvActivated = Ensure-DatrixVenv
if (-not $venvActivated) {
    Write-Error "Failed to activate virtual environment"
    exit 1
}

trap {
    if (Get-Command Disable-DatrixVenv -ErrorAction SilentlyContinue) {
        Disable-DatrixVenv
    }
    throw $_
}

try {
    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $venvPath "bin\python"
    }

    $pyArgs = @("--current", $Current, "--saved", $Saved, "--report", $Report)
    if ($LlmSummary) {
        $pyArgs += @(
            "--llm-summary",
            "--llm-limit", $LlmLimit,
            "--llm-num-predict", $LlmNumPredict,
            "--llm-temperature", $LlmTemperature
        )
        $pyArgs += Get-DatrixLocalLlmArguments -LocalMachines $LocalMachines -LlmModel $LlmModel -LlmTimeoutSeconds $LlmTimeout
    }
    & $pythonExe $pythonScript @pyArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0 -and $Report) {
        $reportFullPath = if ([System.IO.Path]::IsPathRooted($Report)) { $Report } else { Join-Path (Get-DatrixRoot) $Report }
        Write-Host "Report written to: $reportFullPath"
    }

    exit $exitCode
} finally {
    Disable-DatrixVenv
}
