#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Repo-level gate: a run reads user input before generation only through InputSource.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.input_source_census_gate in the shared venv. It parses every
 *.py under datrix-common/src, datrix-language/src and datrix-semantic/src, plus
 datrix-cli/src/datrix_cli/pipeline/stages/parsing.py, with Python ast, leaves out
 fileops/input_source.py, and flags builtin open, a Path read or query method on any receiver that
 is not a known source, os.listdir, os.scandir, os.walk, os.path.exists, os.path.isfile,
 os.path.isdir, and the read helpers of fileops/io.py, utils/transient_io.py and utils/hash.py.

 A receiver is a known source only when it is a name annotated InputSource, self.<attr> declared or
 assigned from one, or .input_source. Every other receiver is reported, so the gate fails closed.

 The flagged modules must equal the gate's exemption table exactly: an unlisted module fails, and so
 does a row that matches no flagged module.

 WHY IT EXISTS: a run can only answer for what it read if every read passes one object. A direct
 read in the analysis packages is a read the run cannot see.

 A built-in self-test runs before every scan: an embedded source with one call of every flagged
 form must flag exactly those, its clean twin nothing, and a planted workspace must report its
 direct reads, pass the same reads through InputSource, and report a stale row and a missing root.

 Exit codes:
   0 = flagged modules equal the exemption table (or the self-test passed, with -SelfTest)
   1 = at least one unlisted module or stale row
   2 = the gate cannot judge: a failed self-test, a missing scanned root, or a source file that
       does not parse or cannot be read

.PARAMETER SelfTest
 Run only the self-test and the wrapper seam checks, and skip the real scan.

.PARAMETER Dbg
 Print the python invocation before running.

.EXAMPLE
 .\input-source-census-gate.ps1
 Compare every flagged module with the exemption table.

.EXAMPLE
 .\input-source-census-gate.ps1 -SelfTest
 Run only the self-test.
#>
[CmdletBinding()]
param(
 [switch]$SelfTest, [switch]$Dbg
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.input_source_census_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
