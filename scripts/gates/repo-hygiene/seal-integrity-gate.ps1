#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if any code outside Node.seal and Node.__deepcopy__ writes a node's seal
 flag.

.DESCRIPTION
 A sealed Node refuses every attribute assignment; the flag that marks it
 sealed lives in its `__dict__` under `_SEAL_FLAG` ("_sealed"). Only the model
 seals or unseals a node: `Node.seal()` and `Node.__deepcopy__` in
 `datrix_common/datrix_model/base.py`. This gate parses every `src/` tree of
 every `datrix-*` package on disk (with `ast`) and fails on any other write of
 the flag:

 - seal-flag-dict-write: `X.__dict__[K]` or `vars(X)[K]` assigned (plain,
   augmented, annotated, unpacked, `for`/`with` target) or deleted, and
   `__setitem__`/`__delitem__`/`pop`/`setdefault`/`update` carrying K on
   `X.__dict__` or `vars(X)`;
 - seal-flag-attribute-write: `X._sealed` assigned or deleted, and
   `setattr`/`delattr`/`__setattr__`/`__delattr__` with key K.

 The terminal state is zero: there is no baseline. The real scan must find the
 write in `Node.seal`, or it exits 2. The non-vacuity self-test runs on every
 invocation before the real scan; -SelfTest runs only that leg.

.PARAMETER Roots
 Comma-separated source trees to scan. When omitted, scans every `datrix-*/src`
 tree on disk. datrix-common's `src` must be among them, or the write in
 `Node.seal` is not found.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\seal-integrity-gate.ps1
 Scan every datrix-*/src tree.

.EXAMPLE
 .\seal-integrity-gate.ps1 -SelfTest
 Prove the scanner reports every planted seal-flag write and nothing else.
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

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\seal_integrity.py") -Arguments $pythonArgs -Gate "seal-integrity" -ShowCommand:$Dbg)
