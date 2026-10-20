#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Cross-language builtin-claims parity gate.

.DESCRIPTION
 Proves every registered `datrix.languages` plugin's declared builtin-group
 claim is sound, over two surfaces, neither with a reviewed-gap path (a
 divergence here is always a real defect):

 1. Claim accounting -- a language's `realized_builtin_groups` names only
    real `BuiltinGroup` members; every group the language is obligated to
    realize (derived from the group's own axis by `obligated_groups`) is in
    its realized set or carried as a `builtin_group:<id>` row in its
    `capability_gaps`; and no group is both realized and rowed (a stale
    row). Each tracked gap row is logged on a live run.
 2. Realized-group mapping coherence -- every `BUILTIN_REGISTRY` row whose
    group the language realizes is actually mapped by that language's
    profile, whether or not the language carries a gap row. Re-derives, as
    an independent belt-and-suspenders backstop, the same judgment
    `register_builtin_capability` enforces at each language's own plugin
    import.

 Derives its target language set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded language literal -- so a future `datrix-codegen-<lang>`
 package is covered automatically with no edit to this gate.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: feeds both comparators planted realized sets (a clean
 language must report nothing; an unknown realized name, an unaccounted
 obligated group, a stale row and an unmapped builtin of a realized group
 must each be reported). Fails loud (exit 2) if fewer than 2 languages are
 registered.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison.

.EXAMPLE
 .\builtin-claims-parity-gate.ps1
 Run the gate for every registered language.

.EXAMPLE
 .\builtin-claims-parity-gate.ps1 -Dbg
 Run the gate with debug logging.

.EXAMPLE
 .\builtin-claims-parity-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.parity.builtin_claims_parity_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
