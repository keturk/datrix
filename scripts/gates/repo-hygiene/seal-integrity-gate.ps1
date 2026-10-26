#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if any code outside Node.seal and Node.__deepcopy__ writes a node's seal
 flag.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.seal_integrity in the shared venv. A sealed Node refuses
 every attribute assignment; the flag that marks it sealed lives in its `__dict__` under
 `_SEAL_FLAG` ("_sealed"). Only the model seals or unseals a node: `Node.seal()` and
 `Node.__deepcopy__` in `datrix_common/datrix_model/base.py`. The gate parses every `src/` tree of
 every `datrix-*` package on disk (with `ast`) and fails on any other write of the flag:

 - seal-flag-dict-write: `X.__dict__[K]` or `vars(X)[K]` assigned (plain,
   augmented, annotated, unpacked, `for`/`with` target) or deleted, and
   `__setitem__`/`__delitem__`/`pop`/`setdefault`/`update` carrying K on
   `X.__dict__` or `vars(X)`;
 - seal-flag-attribute-write: `X._sealed` assigned or deleted, and
   `setattr`/`delattr`/`__setattr__`/`__delattr__` with key K.

 The terminal state is zero: there is no baseline. The real scan must find the
 write in `Node.seal`, or it exits 2. The non-vacuity self-test runs on every
 invocation before the real scan; -SelfTest runs only that leg and the wrapper seam
 checks. The last line is the `[GATE] seal-integrity PASSED|FAILED exit=<n> log=<path>` verdict.

.PARAMETER Roots
 Comma-separated source trees to scan. When omitted, scans every `datrix-*/src`
 tree on disk. datrix-common's `src` must be among them, or the write in
 `Node.seal` is not found.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and the wrapper seam checks, and skip the real scan.

.PARAMETER Dbg
 Print the python invocation first and log at DEBUG level.

.EXAMPLE
 .\seal-integrity-gate.ps1
 Scan every datrix-*/src tree.

.EXAMPLE
 .\seal-integrity-gate.ps1 -SelfTest
 Prove the scanner reports every planted seal-flag write and nothing else.
#>
[CmdletBinding()]
param(
 [string]$Roots = "", [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.seal_integrity" -Parameters $PSBoundParameters
exit $LASTEXITCODE
