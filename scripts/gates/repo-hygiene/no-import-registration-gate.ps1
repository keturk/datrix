#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if importing a framework module registers anything.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.no_import_registration in the shared venv. A registry
 filled as a side effect of importing a module answers differently depending on what was imported
 first. Registries are handed to the run as values instead. The gate parses every `src/` tree of
 every `datrix-*` package on disk (with `ast`) and fails on:

 - a call statement that runs on import (module body, or an if/for/while/try/with/
   class body beneath it; never inside a function) whose callee name contains
   `register`;
 - an `import ... # noqa: F401` whose comment mentions registration.

 The terminal state is zero: there is no baseline and no allowlist. The
 non-vacuity self-test runs on every invocation before the real scan; -SelfTest
 runs only that leg and the wrapper seam checks. The last line is the
 `[GATE] no-import-registration PASSED|FAILED exit=<n> log=<path>` verdict.

.PARAMETER Roots
 Comma-separated source trees to scan. When omitted, scans every `datrix-*/src`
 tree on disk.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and the wrapper seam checks, and skip the real scan.

.PARAMETER Dbg
 Print the python invocation first and log at DEBUG level.

.EXAMPLE
 .\no-import-registration-gate.ps1
 Scan every datrix-*/src tree.

.EXAMPLE
 .\no-import-registration-gate.ps1 -SelfTest
 Prove the scanner reports every planted registration shape and nothing else.
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.no_import_registration" -Parameters $PSBoundParameters
exit $LASTEXITCODE
