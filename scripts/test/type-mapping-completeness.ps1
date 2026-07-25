#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Validate type mapping completeness for specified languages.

.DESCRIPTION
 Runs type mapping completeness validation for one or more language generators.
 Ensures all canonical types in the TypeRegistry have mappings in each language.

.PARAMETER Languages
 Comma-separated list of languages to check (e.g., "python,typescript"). When
 omitted, every registered datrix.languages target is checked (discovered at
 runtime -- never a hardcoded python/typescript list).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.EXAMPLE
 .\type-mapping-completeness.ps1
 Check type mappings for every registered language.

.EXAMPLE
 .\type-mapping-completeness.ps1 -Languages python,typescript
 Check Python and TypeScript type mappings.

.EXAMPLE
 .\type-mapping-completeness.ps1 -Languages python -Dbg
 Check Python type mappings with debug logging.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Languages = "",

    [Parameter()]
    [switch]$Dbg
)

# Error handling - ensure cleanup on exit
$ErrorActionPreference = "Stop"

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
# Get library directory path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\type_mapping_completeness.py"

# Import common modules
$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

# Monorepo workspace root
$datrixRoot = Get-DatrixRoot
$datrixWorkspaceRoot = Get-DatrixWorkspaceRootFromScript -ScriptPath $MyInvocation.MyCommand.Path

# Check if runner script exists
if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: type_mapping_completeness.py not found at: $runnerScript"
    exit 1
}

# Function to handle cleanup on exit
function Invoke-Cleanup {
    Disable-DatrixVenv
}

# Register cleanup handler
trap {
    Invoke-Cleanup
    break
}

# Ensure venv exists and is activated
Ensure-DatrixVenv

try {
    Ensure-DatrixPackagesInstalled

    # Build Python arguments. When -Languages is omitted, the runner defaults to
    # every registered datrix.languages target (discovered at runtime).
    $pythonArgs = @($runnerScript)
    if (-not [string]::IsNullOrWhiteSpace($Languages)) {
        $pythonArgs += @("--languages", $Languages)
    }
    if ($Dbg) {
        $pythonArgs += "--debug"
    }

    # Run the Python script
    $targetLabel = if ([string]::IsNullOrWhiteSpace($Languages)) { "all registered languages" } else { $Languages }
    Write-Host "Running type mapping completeness check for: $targetLabel" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Type mapping completeness check failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Type mapping completeness check passed" -ForegroundColor Green
    exit 0

} finally {
    Invoke-Cleanup
}
