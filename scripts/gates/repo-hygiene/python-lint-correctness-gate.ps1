#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: pyflakes (ruff --select F) findings are a hard zero in every package.

.DESCRIPTION
 Activates the Datrix virtual environment and runs the shared module
 datrix_scripts.python_lint_correctness (scripts/common/lib), which lints the src/ and
 tests/ trees of every workspace datrix* directory holding a pyproject.toml
 (plus the datrix showcase repo's scripts/), discovered at runtime. Each tree
 is linted from its package root so that package's own per-file-ignores
 apply; the rule selection is explicitly F so no package config can hide a
 pyflakes finding.

 HARD ZERO, NO BASELINE: any finding fails. A finding that is genuinely
 required is suppressed only by a line-level `# noqa: <code>` carrying the
 reason on the same line.

 The non-vacuity self-test runs before every scan (a planted F401 + F821 must
 be reported, a clean package must report zero, a fixture per-file-ignores
 must suppress the F401 only), and the live run must scan at least one tree
 for every discovered package.

 Exit codes:
   0 = zero pyflakes findings
   1 = at least one finding, or the self-test failed
   2 = usage error, or ruff could not run

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER Dbg
 Enable DEBUG logging and print the python invocation before running.

.EXAMPLE
 .\python-lint-correctness-gate.ps1
 Lint every package tree in the workspace.

.EXAMPLE
 .\python-lint-correctness-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$commonDir = Join-Path $scriptDir "..\..\common"
# Shared with git/commit-and-push, so it lives in the shared scripts package and runs as a module.
$pythonModule = "datrix_scripts.python_lint_correctness"
$pythonScript = Join-Path $commonDir "lib\datrix_scripts\python_lint_correctness.py"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: python_lint_correctness.py not found at: $pythonScript"
    exit 2
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

trap {
    Write-Host ""
    Write-Warning "Interrupted by user (Ctrl-C)"
    Invoke-Cleanup
    exit 130
}

try {
    $venvActivated = Ensure-DatrixVenv
    if (-not $venvActivated) {
        Write-Error "Failed to activate virtual environment"
        exit 1
    }

    $venvPath = Get-DatrixVenvPath
    $pythonExe = Join-Path $venvPath "Scripts\python.exe"

    $pythonArgs = @("-m", $pythonModule)
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($Dbg) { $pythonArgs += "--debug" }

    if ($Dbg) {
        Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan
        Write-Host "Python script: $pythonScript" -ForegroundColor Cyan
        Write-Host ""
    }

    & $pythonExe @pythonArgs
    exit $LASTEXITCODE

} catch {
    Write-Host ""
    Write-Host "Error occurred:" -ForegroundColor Red
    Write-Host $_.Exception.Message -ForegroundColor Red
    Invoke-Cleanup
    exit 1
} finally {
    Invoke-Cleanup
}
