#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Shared-home body gate: no function outside a shared home may carry the body of a shared-home function.

.DESCRIPTION
 Runs datrix_scripts.gates.parity.shared_home_body_gate. AST-walks every function, public or
 private, of datrix-common, datrix-codegen-kernel and datrix-codegen-common and every function of
 every other datrix-* package's src/ tree. A function qualifies at 8 lines and 40 AST nodes; its body is
 normalized (docstring, annotations and decorators dropped, parameter and local names renamed to
 positional tokens, constants collapsed to their type; attribute names and call targets kept). A
 function whose normalized body equals a home function's in another package is a hit. The
 verdict is a per-package count against the decrease-only pin in
 datrix/scripts/config/shared-home-body-baseline.toml: an increase fails, a decrease passes.

 Runs a plant / observe / revert self-test on every invocation before any real scan is trusted.
 Exits 2 on a self-test failure, an unreadable baseline, an unparseable source file or a missing
 home package.

.PARAMETER Hits
 Print every hit line (copy location and name == home location and name).

.PARAMETER Symbol
 Comma-separated or repeated bare function names; print only the hit lines whose copy has one of
 these names. A report filter only: it never changes the count or the exit code.

.PARAMETER UpdateBaseline
 Seed the baseline from this run when it does not exist; otherwise lower every package's count to
 the live value (keeping seed and reason). Refuses, exit 1, when any count would rise.

.PARAMETER Dbg
 Enable debug logging.

.PARAMETER SelfTest
 Run only the self-test and skip the real scan.

.EXAMPLE
 .\shared-home-body-gate.ps1

.EXAMPLE
 .\shared-home-body-gate.ps1 -Hits

.EXAMPLE
 .\shared-home-body-gate.ps1 -Symbol event_for_replay_plan,_iter_calls
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Hits,

    [Parameter()]
    [string[]]$Symbol,

    [Parameter()]
    [switch]$UpdateBaseline,

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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.parity.shared_home_body_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
