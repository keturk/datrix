#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Detect leftover debug/logging artifacts in source code.

.DESCRIPTION
 Scans Python and TypeScript source files for common debug patterns that should not
 be committed: print() statements, console.log(), logger.warning/debug calls used
 as temporary instrumentation, breakpoint(), debugger statements, and TODO/FIXME
 markers tied to debugging sessions.

 Designed to run as a quick pre-commit or post-fix check to catch "debug scatter"
 before it breaks builds or pollutes the codebase.

 Python files are scanned string-literal-aware: a pattern matching inside a string
 literal is data, not code, and is never reported (e.g. the print() calls in a
 child-process checker script a test embeds as a triple-quoted source string).
 TypeScript files stay line-based.

 A self-test proving both directions (a real artifact is detected; the same artifact
 inside a string literal is not) runs as step 1 of every invocation.

 Exit codes:
   0 = clean (no debug artifacts found)
   1 = debug artifacts detected (prints details)
   2 = usage error, or the self-test failed

.PARAMETER ProjectDir
 One or more project directories to scan (positional). Can be names (e.g., datrix-common)
 or full paths.

.PARAMETER All
 Scan all datrix repositories.

.PARAMETER Strict
 Enable strict mode: also flag logger.debug() and logger.info() calls that contain
 variable interpolation (likely temporary debugging, not permanent logging).

.PARAMETER IncludeGenerated
 Also scan .generated/ directory (normally excluded to focus on source code).

.PARAMETER SelfTest
 Run only the scanner's own detection/false-positive self-test and exit.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\check-debug-artifacts.ps1 datrix-codegen-python
 Scan one project for debug artifacts.

.EXAMPLE
 .\check-debug-artifacts.ps1 -SelfTest
 Run only the self-test (no project argument needed).

.EXAMPLE
 .\check-debug-artifacts.ps1 -All
 Scan all datrix repositories.

.EXAMPLE
 .\check-debug-artifacts.ps1 datrix-common -Strict
 Strict mode: also flag suspicious logger.debug/info with f-strings.
#>

[CmdletBinding()]
param(
 [Parameter()]
 [switch]$All,

 [Parameter(Position=0, ValueFromRemainingArguments=$true)]
 [string[]]$ProjectDir = @(),

 [Parameter()]
 [switch]$Strict,

 [Parameter()]
 [switch]$IncludeGenerated,

 [Parameter()]
 [switch]$SelfTest,

 [Parameter()]
 [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPaths.psm1") -Force
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

# Require -All or ProjectDir (-SelfTest needs neither)
if (-not $SelfTest -and -not $All -and (-not $ProjectDir -or $ProjectDir.Count -eq 0)) {
 Write-Host "Usage:" -ForegroundColor Yellow
 Write-Host "  .\check-debug-artifacts.ps1 -All" -ForegroundColor White
 Write-Host "  .\check-debug-artifacts.ps1 datrix-common [datrix-language ...]" -ForegroundColor White
 Write-Host "  .\check-debug-artifacts.ps1 D:\datrix\datrix-common" -ForegroundColor White
 Write-Host "  .\check-debug-artifacts.ps1 -SelfTest" -ForegroundColor White
 Write-Host ""
 Write-Host "Use Get-Help .\check-debug-artifacts.ps1 -Full for detailed help." -ForegroundColor Yellow
 exit 2
}

# Determine which directories to check (-SelfTest scans nothing; it runs entirely in memory)
$pathsToCheck = @()
if ($All -and -not $SelfTest) {
 $pathsToCheck = @(Get-DatrixDirectoryPaths | Where-Object { Test-Path $_ })
} elseif (-not $SelfTest) {
 $datrixWorkspaceRoot = Get-DatrixWorkspaceRoot
 foreach ($p in $ProjectDir) {
  $fullPath = if ([System.IO.Path]::IsPathRooted($p)) { $p } else { Join-Path $datrixWorkspaceRoot $p }
  if (-not (Test-Path $fullPath)) {
   Write-Host "Error: path not found: $fullPath. Expected a project name under the workspace or a full path." -ForegroundColor Red
   exit 2
  }
  $pathsToCheck += $fullPath
 }
}

$pythonArgs = @($pathsToCheck)
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Strict) { $pythonArgs += "--strict" }
if ($IncludeGenerated) { $pythonArgs += "--include-generated" }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\check_debug_artifacts.py") -Arguments $pythonArgs)
