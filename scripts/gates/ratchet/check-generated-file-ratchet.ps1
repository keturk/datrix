#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Enforce the I5 GeneratedFile-construction ratchet across Datrix packages.

.DESCRIPTION
 Counts direct GeneratedFile(...) constructor calls per package's src/ tree
 and fails if any package's count exceeds its frozen baseline at
 scripts/config/generated-file-ratchet.json.

 Exit codes:
   0 = clean (no regressions), -Warn mode, or a successful -UpdateBaseline
   1 = a package's count exceeds its frozen baseline
   2 = usage error, missing baseline, or an attempted baseline increase

.PARAMETER Warn
 Warning mode: report regressions but exit 0.

.PARAMETER ShowFiles
 Print each file being scanned (verbose mode).

.PARAMETER BaseDir
 Monorepo root directory (default: auto-detect).

.PARAMETER UpdateBaseline
 Recompute current counts and write the frozen baseline. If no baseline
 file exists yet, this is the bootstrap freeze and always succeeds. If a
 baseline already exists, this only succeeds when every package's new count
 is <= its existing baseline (monotonic ratchet: tighten, never loosen).

.PARAMETER SelfTest
 Run only the self-test suite (plain-Python edge-case checks on the scanner's
 own functions) and exit -- skips the real package scan. The same self-test
 also runs automatically, unconditionally, as step 1 of every normal
 invocation (with or without this switch).

.PARAMETER Dbg
 Print the interpreter and arguments before running.

.EXAMPLE
 .\check-generated-file-ratchet.ps1
 Scan all packages, fail on regressions (self-test runs first, automatically).

.EXAMPLE
 .\check-generated-file-ratchet.ps1 -SelfTest
 Run only the scanner's own self-test suite.

.EXAMPLE
 .\check-generated-file-ratchet.ps1 -UpdateBaseline
 Freeze the initial baseline, or tighten it after a migration task reduces a package's count.
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

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($Warn) { $pythonArgs += "--warn" }
if ($ShowFiles) { $pythonArgs += "--verbose" }
if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }
if ($UpdateBaseline) { $pythonArgs += "--update-baseline" }
if ($SelfTest) { $pythonArgs += "--self-test" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\check_generated_file_ratchet.py") -Arguments $pythonArgs -Gate "generated-file-ratchet" -ShowCommand:$Dbg)
