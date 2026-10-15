#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: a name never goes str() -> to_*_case().

.DESCRIPTION
 Activates the Datrix virtual environment and runs the shared module
 datrix_scripts.polystring_case_roundtrip (scripts/common/lib), which parses every
 publishable .py file in the datrix showcase repo and every datrix-* clone in
 the workspace (discovered at runtime) and fails on any call to a
 datrix_common.utils.text case function whose argument is:

   str-wrapped  to_X_case(str(E))
   str-bound    to_X_case(NAME) where NAME = str(E) is bound in the same scope
   nested       to_X_case(to_Y_case(E))
   simple-name  to_X_case(extract_simple_name(E))

 WHY IT EXISTS: every identifier the generator re-cases is a PolyString that
 split its words once and exposes .snake/.camel/.pascal/.kebab/
 .screaming_snake/.simple. The round trip -- str() the name, then re-case the
 text -- throws the variants away, recomputes the split, and hides from the
 next reader that the value was a name. It spread to several hundred sites
 before anything refused it; the Semgrep rule that named the shape ran only
 on demand, as a WARNING. This gate is held at a HARD ZERO with no exemption
 file, because no shape above has a legitimate instance.

 The non-vacuity self-test runs before every scan: one planted instance of
 every shape and callee spelling must be detected at its exact line, a clean
 source must yield zero, and an unparseable source must refuse rather than
 report clean.

 Exit codes:
   0 = zero round trips in every scanned file
   1 = at least one round trip, or the self-test failed
   2 = usage error, or a scanned file could not be parsed

.PARAMETER Repo
 Limit the scan to these repo names. Default: every framework repo in the workspace.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER PendingOnly
 Scan only the files a `git add -A` would stage in each repo (the commit-path form).

.PARAMETER Dbg
 Enable DEBUG logging and print the python invocation before running.

.EXAMPLE
 .\polystring-case-roundtrip-gate.ps1
 Scan every framework repo in the workspace.

.EXAMPLE
 .\polystring-case-roundtrip-gate.ps1 -Repo datrix-codegen-aws
 Scan only the named repo(s).

.EXAMPLE
 .\polystring-case-roundtrip-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string[]]$Repo,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$PendingOnly,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
# `powershell -File` binds "a,b" as one string rather than an array, so
# split every element on commas: a repo name never contains one.
foreach ($name in ($Repo -split ",")) {
    $trimmed = $name.Trim()
    if ($trimmed) { $pythonArgs += @("--repo", $trimmed) }
}
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($PendingOnly) { $pythonArgs += "--pending-only" }
if ($Dbg) { $pythonArgs += "--debug" }

# Shared with git/commit-and-push, so it lives in the shared scripts package and runs as a module.
exit (Invoke-DatrixPythonScript -Module "datrix_scripts.polystring_case_roundtrip" -Arguments $pythonArgs -Gate "polystring-case-roundtrip" -ShowCommand:$Dbg)
