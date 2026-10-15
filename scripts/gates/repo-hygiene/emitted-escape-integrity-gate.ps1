#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if a Python-emitting Jinja template escapes an escape sequence.

.DESCRIPTION
 Jinja copies template text through verbatim, so a doubled backslash before n, t
 or r in a '*.py.j2' template reaches the emitted Python source still doubled --
 an escaped BACKSLASH rather than the escape that was meant. The generated
 program then builds a string carrying two literal characters where a line break
 belonged.

 Nothing downstream notices. The emitted Python compiles, the function writing
 the artifact returns the right count, and any validator that accepts comments
 passes. It was found in production as a gateway trusted-peer fragment whose
 whole body landed on one physical line behind a leading '#', so every directive
 in it was read as part of that comment and the proxy trusted nobody -- through a
 green smoke gate and a successful deploy.

 Scope is templates that emit PYTHON. Templates emitting shell, TypeScript or a
 regex are excluded: a doubled backslash is ordinary and correct in all three.

 The package set is walked from disk, so a new datrix-codegen-<lang> package is
 covered with no edit here.

 The non-vacuity self-test runs on EVERY invocation before the real scan, so a
 green result can never mean "the detector was broken". It covers all three run
 lengths -- one backslash (correct), two (the defect), four (a deliberate deeper
 escape) -- because the run length is the rule. Use -SelfTest to run only that leg.

 A legitimately doubled escape is a reviewed entry in
 scripts/config/emitted-escape-exemptions.json, pinned to the file and the exact
 line, with a written reason and a pinned count -- never silence.

 Exit codes:
   0 = clean (no escaped escapes outside the reviewed exemptions)
   1 = an escaped escape was found, or an exemption matches nothing any more
   2 = usage error, an unreadable/self-inconsistent exemptions baseline, no
       templates discovered (which would pass vacuously), or a failing self-test

.PARAMETER BaseDir
 Workspace root to scan. Defaults to the workspace holding this checkout.

.PARAMETER ShowFiles
 Print every template being scanned.

.PARAMETER SelfTest
 Run only the detector's non-vacuity self-test and exit.

.EXAMPLE
 .\emitted-escape-integrity-gate.ps1
 Scan every Python-emitting template in the monorepo.

.EXAMPLE
 .\emitted-escape-integrity-gate.ps1 -ShowFiles
 Scan and list each template as it is read.

.EXAMPLE
 .\emitted-escape-integrity-gate.ps1 -SelfTest
 Prove the detector fires on a doubled escape and leaves the other run lengths alone.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$BaseDir = "",

    [Parameter()]
    [switch]$ShowFiles,

    [Parameter()]
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($SelfTest) {
    $pythonArgs += "--self-test"
}
else {
    if ($BaseDir) { $pythonArgs += @("--base-dir", $BaseDir) }
    if ($ShowFiles) { $pythonArgs += "--show-files" }
}

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\emitted_escape_integrity.py") -Arguments $pythonArgs -Gate "emitted-escape-integrity")
