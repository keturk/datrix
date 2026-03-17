#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Rebuild Tree-sitter Parser for Datrix DSL (PowerShell Wrapper)

.DESCRIPTION
 This is a simple wrapper that calls the Python rebuild_parser.py script.
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

# Script directory
$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path

# Python script path (in library/dev subdirectory)
$pythonScript = Join-Path (Split-Path -Parent $scriptDir) "library\dev\rebuild_parser.py"

# Check if Python script exists
if (-not (Test-Path $pythonScript)) {
 Write-Error "Python script not found: $pythonScript"
 exit 1
}

# Find Python executable
$pythonExe = $null

# Try to find Python in common locations
$pythonCommands = @(
 "python",
 "python3",
 "py",
 "py -3"
)

foreach ($cmd in $pythonCommands) {
 try {
 $testResult = & { $ErrorActionPreference = 'SilentlyContinue'; & $cmd --version 2>&1 }
 if ($LASTEXITCODE -eq 0) {
 $pythonExe = $cmd
 break
 }
 } catch {
 continue
 }
}

if (-not $pythonExe) {
 Write-Error "Python not found. Please install Python 3.9 or later."
 Write-Host ""
 Write-Host "Download Python from: https://www.python.org/downloads/" -ForegroundColor Yellow
 exit 1
}

# Build arguments
$pythonArgs = @($pythonScript)
if ($Force) {
 $pythonArgs += "--force"
}
if ($DebugPreference -ne 'SilentlyContinue') {
 $pythonArgs += "--debug"
}

# Execute Python script
& $pythonExe @pythonArgs
exit $LASTEXITCODE
