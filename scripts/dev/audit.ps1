<#
.SYNOPSIS
    Audit generated Python code for placeholders and syntax errors.

.DESCRIPTION
    Scans .generated/python/docker for:
    - Python syntax errors (ast.parse)
    - Placeholder patterns: pass, raise NotImplementedError, "# Test fixtures placeholder"
    Run from repository root (directory containing .generated and datrix).
    When -Report is used, the report is written to the given path under the repository root
    (e.g. examples-generated-audit-report.md -> <repo>\examples-generated-audit-report.md).

.PARAMETER OutputBase
    Output base directory (default: .generated).

.PARAMETER Report
    Write markdown report to this path under repository root (e.g. examples-generated-audit-report.md).
    Script reports the full path where the report was written.

.PARAMETER FailOnSyntax
    Exit with non-zero if any syntax errors are found.

.PARAMETER FailOnPlaceholders
    Exit with non-zero if any placeholder patterns are found (actionable only; allowlisted excluded).

.EXAMPLE
    .\audit.ps1 -Report examples-generated-audit-report.md
    Run audit and write markdown report; script prints where the report was written.

.EXAMPLE
    .\audit.ps1 -Report examples-generated-audit-report.md -FailOnSyntax -FailOnPlaceholders
    Run audit, write report, and exit non-zero if syntax errors or actionable placeholders.
#>
[CmdletBinding()]
param(
    [string]$OutputBase = ".generated",
    [string]$Report = "",
    [switch]$FailOnSyntax,
    [switch]$FailOnPlaceholders
)

# Show usage when no parameters provided (mimic compile.ps1)
if ($PSBoundParameters.Count -eq 0) {
    Write-Host "Usage:" -ForegroundColor Yellow
    Write-Host "  .\audit.ps1 -Report <path>" -ForegroundColor White
    Write-Host "  .\audit.ps1 -Report examples-generated-audit-report.md [-FailOnSyntax] [-FailOnPlaceholders]" -ForegroundColor White
    Write-Host ""
    Write-Host "Report path is under repository root. Use Get-Help .\audit.ps1 -Full for detailed help." -ForegroundColor Yellow
    exit 1
}

# Deactivate venv on exit (normal exit or Ctrl+C)
trap {
    if (Get-Command Disable-DatrixVenv -ErrorAction SilentlyContinue) {
        Disable-DatrixVenv
    }
    throw $_
}

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
$pythonScript = Join-Path $libraryDir "dev\audit_generated.py"

. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "audit_generated.py not found at: $pythonScript"
    exit 1
}

$venvActivated = Ensure-DatrixVenv
if (-not $venvActivated) {
    Write-Error "Failed to activate virtual environment"
    exit 1
}

try {
    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"
    if (-not (Test-Path $pythonExe)) {
        $pythonExe = Join-Path $venvPath "bin\python"
    }

    $pyArgs = @("--output-base", $OutputBase)
    if ($Report) {
        $pyArgs += "--report"
        $pyArgs += $Report
    }
    if ($FailOnSyntax) { $pyArgs += "--fail-on-syntax" }
    if ($FailOnPlaceholders) { $pyArgs += "--fail-on-placeholders" }

    & $pythonExe $pythonScript @pyArgs
    $exitCode = $LASTEXITCODE

    if ($Report) {
        $reportFullPath = if ([System.IO.Path]::IsPathRooted($Report)) { $Report } else { Join-Path (Get-DatrixRoot) $Report }
        Write-Host "Report written to: $reportFullPath"
    }

    exit $exitCode
} finally {
    Disable-DatrixVenv
}
