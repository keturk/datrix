<#
.SYNOPSIS
    Check parity between Python and TypeScript codegen implementations.

.DESCRIPTION
    Compares builtins and type mappings between datrix-codegen-python and
    datrix-codegen-typescript to identify missing implementations and
    inconsistencies. Writes a Markdown report with detailed findings.

.PARAMETER Report
    Output report path under datrix root (default: parity-check-report.md).

.EXAMPLE
    .\parity-checker.ps1
    Run parity check and write report to datrix_root\parity-check-report.md.

.EXAMPLE
    .\parity-checker.ps1 -Report custom-parity-report.md
    Write report to datrix_root\custom-parity-report.md.
#>
[CmdletBinding()]
param(
    [string]$Report = "parity-check-report.md"
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
$pythonScript = Join-Path $libraryDir "dev\parity_checker.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "parity_checker.py not found at: $pythonScript"
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

    $pyArgs = @("--report", $Report)
    & $pythonExe $pythonScript @pyArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -eq 0 -and $Report) {
        $reportFullPath = if ([System.IO.Path]::IsPathRooted($Report)) { $Report } else { Join-Path (Get-DatrixRoot) $Report }
        Write-Host "`nReport written to: $reportFullPath" -ForegroundColor Green
    }

    exit $exitCode
} finally {
    Disable-DatrixVenv
}
