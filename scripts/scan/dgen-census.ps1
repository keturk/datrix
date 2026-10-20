#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Per-domain census of one dgen target's compiled DAL generator definitions.

.DESCRIPTION
 The behaviour is datrix_scripts.scan.dgen_census. Walks every domain of the target's
 compiled GeneratorDefinition IR, counting declared file clauses (domain-level
 plus recursive iteration/children block files) and domain builders, and flags
 double-emit offenders (domains that declare files while keeping an imperative
 domain builder); any offender gates the exit code. The target name is resolved
 against the installed datrix.platforms / datrix.dgen_generator_targets
 entry points at runtime -- the target set is never hardcoded. Output:
 <workspace>\.tmp\dev\dgen-census-<language>.json.
 The script's own non-vacuity self-test (proves the double-emit comparator
 detects a forced synthetic defect and leaves a clean domain alone) runs
 automatically as step 1 of every census; a self-test failure aborts before
 any real finding is reported. Pass -SelfTest to run only the self-test.

 Exit codes: 0 no double-emit offenders, 1 at least one, 2 no, unknown or
 definition-less -Language, or the self-test failed.

.PARAMETER Language
 Installed dgen target name (e.g. python). Unknown names fail loud listing
 every installed target. Not required with -SelfTest.

.PARAMETER Output
 Override the output JSON path.

.PARAMETER Dbg
 Enable debug logging in the Python module.

.PARAMETER SelfTest
 Run only the module's self-test (the double-emit comparator detects a forced
 defect, a census without -Language is refused, the wrapper seam holds) and
 skip the real census; no -Language needed.

.EXAMPLE
 .\dgen-census.ps1 python

.EXAMPLE
 .\dgen-census.ps1 typescript -Output D:\datrix\.tmp\dev\ts-census.json

.EXAMPLE
 .\dgen-census.ps1 -SelfTest
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)][string]$Language,
    [string]$Output,
    [switch]$Dbg,
    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.scan.dgen_census" -Parameters $PSBoundParameters
exit $LASTEXITCODE
