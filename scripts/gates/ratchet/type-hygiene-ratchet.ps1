#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Enforce the per-package type-hygiene ratchet across Datrix packages.

.DESCRIPTION
 Counts type-ignore comments, functions with Any in a signature, and cast calls
 per package's src/ tree and fails if any count exceeds its frozen baseline at
 scripts/config/type-hygiene-ratchet.json. The type checker is never run.

 Exit codes:
   0 = every count at or below its baseline, -Warn mode, or a successful -UpdateBaseline
   1 = a count exceeds its baseline
   2 = usage error, missing or malformed baseline, an unreadable or unparsable
       file, an attempted baseline increase, or a failed self-test step

.PARAMETER Warn
 Warning mode: report a rise but exit 0.

.PARAMETER ShowFiles
 Print each file being scanned.

.PARAMETER BaseDir
 Workspace root directory (default: auto-detect).

.PARAMETER UpdateBaseline
 Write the current counts. If no baseline file exists this is the first
 freeze. If one exists, this only succeeds when no count rises; a rise is
 refused with exit 2 and the baseline is left unchanged.

.PARAMETER SelfTest
 Run only the self-test over a planted workspace and exit; reads nothing of
 the real workspace. The same checks also run automatically before every real
 scan.

.PARAMETER Dbg
 Print the interpreter and arguments before running.

.EXAMPLE
 .\type-hygiene-ratchet.ps1
 Scan all packages, fail on a rise (the self-test runs first, automatically).

.EXAMPLE
 .\type-hygiene-ratchet.ps1 -SelfTest
 Run only the census self-test.

.EXAMPLE
 .\type-hygiene-ratchet.ps1 -UpdateBaseline
 Freeze the first baseline, or bank a fall after a burn-down.
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
    [switch]$UpdateBaseline,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.ratchet.type_hygiene_ratchet" -Parameters $PSBoundParameters
exit $LASTEXITCODE
