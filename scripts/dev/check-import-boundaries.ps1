#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Enforce cross-package import boundary rules for Datrix monorepo.

.DESCRIPTION
 Scans all Python source files in each package's src/ directory and checks imports
 against forbidden prefix rules. Uses AST parsing - no package installation required.

 Enforces architectural dependency rules documented in:
 datrix-common/docs/architecture/import-boundaries.md

 Exit codes:
   0 = clean (no violations) or -Warn mode
   1 = violations found in fail mode
   2 = usage error or configuration error

.PARAMETER Warn
 Warning mode: report violations but exit 0 (default is fail mode: exit 1 on violations)

.PARAMETER ShowFiles
 Print each file being scanned (verbose mode)

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect by walking up from script location)

.PARAMETER CheckTargetLiterals
 Run the I1 target-literal ratchet check (design 023, invariant I1) in addition
 to the import-boundary check. Compares current per-file target-literal counts
 against the frozen baseline at scripts/config/target-literal-baseline.toml.

.PARAMETER UpdateBaseline
 Recompute current per-file counts and overwrite the frozen baseline(s), then
 exit 0. Updates target-literal-baseline.toml unless -CheckProviderConditionals
 is passed (without -CheckTargetLiterals), in which case it updates
 provider-conditional-baseline.toml instead. Pass both -CheckTargetLiterals and
 -CheckProviderConditionals to update both baselines in one run.

.PARAMETER CheckProviderConditionals
 Run the I6 successor ratchet check (design 023, invariant I6, DI-4/DI-5) in
 addition to the import-boundary check. Compares current per-file
 platform-identity-conditional counts in the language packages
 (datrix_codegen_python, datrix_codegen_typescript) against the frozen
 baseline at scripts/config/provider-conditional-baseline.toml.

.PARAMETER CheckFunctionLevelImports
 Run the function-level-import ratchet check (design 029, D4/I6, task 17-09)
 in addition to the import-boundary check. Compares current per-file
 function-level-import counts in datrix-common's src/ tree ONLY against the
 frozen baseline at scripts/config/function-level-import-baseline.toml.

.PARAMETER SelfTest
 Run only the self-test suite (rule-model, AST-scanner, and ratchet
 invariants, including a real mutation-based CLI non-vacuity proof) and
 exit -- does not run the import-boundary scan itself. The self-test also
 runs automatically as step 1 of every OTHER invocation of this script
 (with or without this switch); pass -SelfTest to run only the self-test.

.PARAMETER Dbg
 Enable debug logging

.EXAMPLE
 .\check-import-boundaries.ps1
 Scan all packages (self-test runs first automatically), fail on violations

.EXAMPLE
 .\check-import-boundaries.ps1 -Warn
 Warning mode: report violations but exit 0

.EXAMPLE
 .\check-import-boundaries.ps1 -ShowFiles
 Show each file being scanned

.EXAMPLE
 .\check-import-boundaries.ps1 -BaseDir D:\datrix
 Specify monorepo root explicitly

.EXAMPLE
 .\check-import-boundaries.ps1 -CheckTargetLiterals
 Run the I1 target-literal ratchet check against the frozen baseline

.EXAMPLE
 .\check-import-boundaries.ps1 -CheckTargetLiterals -UpdateBaseline
 Recompute and overwrite the frozen target-literal baseline

.EXAMPLE
 .\check-import-boundaries.ps1 -CheckProviderConditionals
 Run the I6 successor (provider-conditional) ratchet check against the frozen baseline

.EXAMPLE
 .\check-import-boundaries.ps1 -CheckProviderConditionals -UpdateBaseline
 Recompute and overwrite the frozen provider-conditional baseline

.EXAMPLE
 .\check-import-boundaries.ps1 -CheckFunctionLevelImports
 Run the function-level-import ratchet check (design 029, D4/I6) against the frozen baseline

.EXAMPLE
 .\check-import-boundaries.ps1 -CheckFunctionLevelImports -UpdateBaseline
 Recompute and overwrite the frozen function-level-import baseline

.EXAMPLE
 .\check-import-boundaries.ps1 -SelfTest
 Run only the self-test suite (rule model, scanners, ratchets, CLI mutation proof)
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Warn,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$CheckTargetLiterals,

    [Parameter()]
    [switch]$UpdateBaseline,

    [Parameter()]
    [switch]$CheckProviderConditionals,

    [Parameter()]
    [switch]$CheckFunctionLevelImports,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "check-import-boundaries.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixPaths.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Check if Python script exists
if (-not (Test-Path $pythonScript)) {
    Write-Error "Error: check-import-boundaries.py not found at: $pythonScript"
    exit 2
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
    $pythonArgs = @($pythonScript)
    if ($Warn) { $pythonArgs += "--warn" }
    if ($ShowFiles) { $pythonArgs += "--verbose" }
    if ($BaseDir) { $pythonArgs += "--base-dir"; $pythonArgs += $BaseDir }
    if ($CheckTargetLiterals) { $pythonArgs += "--check-target-literals" }
    if ($UpdateBaseline) { $pythonArgs += "--update-baseline" }
    if ($CheckProviderConditionals) { $pythonArgs += "--check-provider-conditionals" }
    if ($CheckFunctionLevelImports) { $pythonArgs += "--check-function-level-imports" }
    if ($SelfTest) { $pythonArgs += "--self-test" }

    # Debug output if requested
    if ($Dbg) {
        Write-Host "Python executable: $pythonExe" -ForegroundColor Cyan
        Write-Host "Python script: $pythonScript" -ForegroundColor Cyan
        Write-Host "Arguments: $($pythonArgs -join ' ')" -ForegroundColor Cyan
        Write-Host ""
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
