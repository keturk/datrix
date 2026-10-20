#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Detect leftover debug/logging artifacts in source code.

.DESCRIPTION
 The behaviour is datrix_scripts.scan.check_debug_artifacts. Scans Python and TypeScript
 source files for common debug patterns that should not be committed: print() statements,
 console.log(), logger.warning/debug calls used as temporary instrumentation, breakpoint(),
 debugger statements, and TODO/FIXME markers tied to debugging sessions.

 Designed to run as a quick pre-commit or post-fix check to catch "debug scatter"
 before it breaks builds or pollutes the codebase.

 Python files are scanned string-literal-aware: a pattern matching inside a string
 literal is data, not code, and is never reported (e.g. the print() calls in a
 child-process checker script a test embeds as a triple-quoted source string).
 TypeScript files stay line-based.

 A self-test proving both directions (a real artifact is detected; the same artifact
 inside a string literal is not) runs as step 1 of every scan. -All wins over named
 projects.

 Exit codes:
   0 = clean (no debug artifacts found)
   1 = debug artifacts detected (prints details)
   2 = usage error (nothing selected, a path that does not exist), or the self-test failed

.PARAMETER All
 Scan all datrix repositories.

.PARAMETER ProjectDir
 One or more project directories to scan (positional). Can be names (e.g., datrix-common)
 or full paths.

.PARAMETER Strict
 Enable strict mode: also flag logger.debug() and logger.info() calls that contain
 variable interpolation (likely temporary debugging, not permanent logging).

.PARAMETER IncludeGenerated
 Also scan .generated/ directory (normally excluded to focus on source code).

.PARAMETER SelfTest
 Run only the module's self-test: the detection/false-positive check, the usage when nothing
 is selected, the refusal of a missing path, and the wrapper seam. No project argument needed.

.PARAMETER Dbg
 Print each file scanned and each finding's matching line.

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
    [switch]$All,
    [Parameter(Position = 0, ValueFromRemainingArguments = $true)][string[]]$ProjectDir,
    [switch]$Strict,
    [switch]$IncludeGenerated,
    [switch]$SelfTest,
    [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.check_debug_artifacts" -Parameters $PSBoundParameters
exit $LASTEXITCODE
