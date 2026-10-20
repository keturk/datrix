#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Fail if a `from <datrix module> import <name>` names something that does not exist.

.DESCRIPTION
 Runs datrix_scripts.gates.repo_hygiene.import_name_existence_gate in the shared venv.

 A half-completed rename leaves a module importing one name and defining
 another. When the import runs, the first test that touches the module raises
 ImportError and the suite goes red. When it sits inside `if TYPE_CHECKING:`,
 nothing happens at all -- the block never executes, every package still
 imports cleanly, and this repository runs no standalone type-checker by
 policy. Every annotation written against that name is then meaningless, and
 nothing will ever say so.

 This gate resolves every `from <module> import <name>` whose module belongs to
 a Datrix package against whether the name actually exists there, by three
 routes in order: a module-level binding in that module's own source (AST,
 including its own TYPE_CHECKING block), a submodule of that module, and
 finally a runtime attribute after importing it. Runtime imports are checked
 alongside TYPE_CHECKING ones because it costs nothing once the resolver
 exists.

 Deliberate negative-existence assertions -- an import inside
 `pytest.raises(ImportError)` or `try/except ImportError`, written to prove a
 deleted symbol is gone -- are excluded and counted, never reported.

 The terminal state is zero. There is no baseline and no ratchet: a name that
 resolves by none of the three routes is a defect in the importing module.

 The non-vacuity self-test runs on EVERY invocation before the real scan, so a
 green result can never mean "the resolver was broken". Use -SelfTest to run
 only that leg.

.PARAMETER Roots
 Comma-separated directories to scan. When omitted, scans every `src/` and
 `tests/` tree of every `datrix*` package repo plus the showcase repo's
 `scripts/` tree, derived from what is on disk.

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real scan.

.EXAMPLE
 .\import-name-existence-gate.ps1
 Scan every Datrix package tree.

.EXAMPLE
 .\import-name-existence-gate.ps1 -Roots D:/datrix/datrix-common/src
 Scan a single tree.

.EXAMPLE
 .\import-name-existence-gate.ps1 -SelfTest
 Prove the resolver flags planted dead names and leaves every documented
 false-positive family alone.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$Roots = "",

    [Parameter()]
    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.repo_hygiene.import_name_existence_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
