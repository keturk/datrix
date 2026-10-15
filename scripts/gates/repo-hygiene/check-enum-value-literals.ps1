#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Hard-zero gate: no generator may branch on a user enum's member values.

.DESCRIPTION
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

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($ShowFiles) { $pythonArgs += "--verbose" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\check_enum_value_literals.py") -Arguments $pythonArgs -Gate "enum-value-literals" -ShowCommand:$Dbg)
