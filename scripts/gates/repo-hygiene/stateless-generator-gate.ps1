#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if a generator holds run state: an attribute assigned after construction,
 or a constructor that takes the run context.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.stateless_generator in the shared venv. A generator is a
 function of (Application, CodegenContext, output_dir). The gate parses every `src/` tree of every
 `datrix-*` package on disk (with `ast`), finds every `Generator` subclass from the class graph
 (bases resolved through imports and re-exports), and fails on:

 - an assignment to an attribute of `self` (or `cls`) in any method of such a
   class other than `__init__` (plain, augmented, annotated, `for`/`with`
   targets, unpacking, `setattr`, `self.__dict__[...]`);
 - an assignment to an attribute of a name typed as such a class (a parameter
   or variable annotation, or a `for` target iterating one), anywhere;
 - a parameter of such a class's `__init__` typed `CodegenContext`.

 The terminal state is zero: there is no baseline and no allowlist. The
 non-vacuity self-test runs on every invocation before the real scan; -SelfTest
 runs only that leg and the wrapper seam checks. The last line is the
 `[GATE] stateless-generator PASSED|FAILED exit=<n> log=<path>` verdict.

.PARAMETER Roots
 Comma-separated source trees to scan. When omitted, scans every `datrix-*/src`
 tree on disk. The kernel's `src` must be among them, or no generator is found.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and the wrapper seam checks, and skip the real scan.

.PARAMETER Dbg
 Print the python invocation first and log at DEBUG level.

.EXAMPLE
 .\stateless-generator-gate.ps1
 Scan every datrix-*/src tree.

.EXAMPLE
 .\stateless-generator-gate.ps1 -SelfTest
 Prove the scanner reports every planted run-state shape and nothing else.
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.stateless_generator" -Parameters $PSBoundParameters
exit $LASTEXITCODE
