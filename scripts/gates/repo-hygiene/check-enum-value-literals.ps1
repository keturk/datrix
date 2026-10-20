#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Hard-zero gate: no generator may branch on a user enum's member values.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.check_enum_value_literals in the shared venv, which
 AST-scans every scanned package's src/ tree for two shapes:

   A. <expr>.get_value("X") / .require_value("X")  -- member looked up by literal
   B. "X" in value_names / member_names / ...      -- literal tested against a
                                                      collection of member names

 A .dtrx enum's members are the declaring project's vocabulary. A generator that
 reads one by literal name turns somebody else's spelling into policy: rename the
 member and the behaviour silently vanishes; name an unrelated enum the same way
 and it silently appears. Declared contracts (see work { }) reference the model
 instead.

 The baseline is a hard zero with no exemption file, on purpose: a legitimate
 need to branch on a member value is a design defect, not an entry to record.

 The scanner's own self-test runs first on every invocation -- it plants one
 instance of each shape and requires both to be found, and requires clean source
 to report none -- so a scanner that can only return zero fails here rather than
 being believed.

 Exit codes:
   0 = clean, or a successful -SelfTest run
   1 = a violation was found
   2 = usage error, no packages discovered, or the self-test failed

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect).

.PARAMETER SelfTest
 Run only the scanner's self-test and exit, skipping the real scan.

.PARAMETER ShowFiles
 Print each file as it is scanned.

.PARAMETER Dbg
 Print the interpreter and arguments before running.

.EXAMPLE
 .\check-enum-value-literals.ps1
 Scan every package, fail on any violation.

.EXAMPLE
 .\check-enum-value-literals.ps1 -SelfTest
 Prove the scanner detects both shapes, without scanning the tree.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.check_enum_value_literals" -Parameters $PSBoundParameters
exit $LASTEXITCODE
