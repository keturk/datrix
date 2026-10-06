#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Rebuild Tree-sitter Parser for Datrix DSL (PowerShell Wrapper)

.DESCRIPTION
 Activates the Datrix virtual environment and runs lib\rebuild_parser.py.
 The actual logic is implemented in Python for better cross-platform compatibility.

.PARAMETER Force
 Force rebuild even if grammar hasn't changed

.EXAMPLE
 .\rebuild-parser.ps1
 Rebuild the parser from grammar.js

.EXAMPLE
 .\rebuild-parser.ps1 -Force
 Force rebuild even if grammar hasn't changed
#>

[CmdletBinding()]
param(
 [switch]$Force
)

# Error handling
$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$pythonScript = Join-Path $scriptDir "lib\rebuild_parser.py"
$commonDir = Join-Path $scriptDir "..\common"
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $pythonScript)) {
 Write-Error "Python script not found: $pythonScript"
 exit 1
}

$venvActivated = Ensure-DatrixVenv
if (-not $venvActivated) {
 Write-Error "Failed to activate virtual environment"
 exit 1
}
$pythonExe = Join-Path (Get-DatrixVenvPath) "Scripts\python.exe"

# Build arguments
$pythonArgs = @($pythonScript)
if ($Force) {
 $pythonArgs += "--force"
}
if ($DebugPreference -ne 'SilentlyContinue') {
 $pythonArgs += "--debug"
}

& $pythonExe @pythonArgs
exit $LASTEXITCODE
