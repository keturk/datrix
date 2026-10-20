#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if importing a framework module registers anything.

.DESCRIPTION
 A registry filled as a side effect of importing a module answers differently
 depending on what was imported first. Registries are handed to the run as values
 instead. This gate parses every `src/` tree of every `datrix-*` package on disk
 (with `ast`) and fails on:

 - a call statement that runs on import (module body, or an if/for/while/try/with/
   class body beneath it; never inside a function) whose callee name contains
   `register`;
 - an `import ... # noqa: F401` whose comment mentions registration.

 The terminal state is zero: there is no baseline and no allowlist. The
 non-vacuity self-test runs on every invocation before the real scan; -SelfTest
 runs only that leg.

.PARAMETER Roots
 Comma-separated source trees to scan. When omitted, scans every `datrix-*/src`
 tree on disk.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\no-import-registration-gate.ps1
 Scan every datrix-*/src tree.

.EXAMPLE
 .\no-import-registration-gate.ps1 -SelfTest
 Prove the scanner reports every planted registration shape and nothing else.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Roots = "",

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
if ($SelfTest) {
    $pythonArgs += "--self-test"
}
elseif (-not [string]::IsNullOrWhiteSpace($Roots)) {
    $pythonArgs += "--roots"
    foreach ($item in $Roots.Split(",")) {
        $trimmed = $item.Trim()
        if (-not [string]::IsNullOrWhiteSpace($trimmed)) { $pythonArgs += $trimmed }
    }
}

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\no_import_registration.py") -Arguments $pythonArgs -Gate "no-import-registration" -ShowCommand:$Dbg)
