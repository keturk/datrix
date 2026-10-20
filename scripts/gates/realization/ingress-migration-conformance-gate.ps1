#!/usr/bin/env pwsh
<#
.SYNOPSIS
    Declaration-driven service ingress conformance gate.

.DESCRIPTION
    Repo-level proof that the framework's own showcase examples
    (datrix/examples/**) conform to the declaration-driven ingress derivation: a
    service's exposure follows what the system declares, never its name. This is
    a repo-level validation SCRIPT -- the `datrix` showcase repo hosts no pytest
    suite -- exit 0 iff every assertion below holds.

    Regenerates three representative registered example projects individually
    (single-project explicit-output generation -- never a group generation for
    that step), plus separately runs the full-tree example generation
    (`run-complete -All -Skip3 -Skip4`, syntax + codegen only, over every
    registered example) -- a distinct, independently-justified action from the
    targeted per-project regeneration.

    Asserts every realized-exposure delta falls in exactly four classes:
      (a) all-auth(service) surfaces leave the public edge (INTERNAL derivation,
          no gateway route, loopback-only/unpublished port)
      (b) previously name-suppressed external APIs gain gateway routes (name-
          blindness mechanism -- NOT independently reproducible from any
          registered example; see "Delta class (b)" below)
      (c) docker gateway existence follows the declaration (declared -> emitted
          even single-service)
      (d) the migrated webhook endpoint generates an unchanged verification
          prelude (mode-only change), proven at the source level: every webhook
          verification artifact dispatches only on its verify-mode field and
          carries no AuthMode dependence, so the rendered prelude is a pure
          function of the unchanged verify(...) contract (no stored output
          snapshot is involved -- the repo keeps none)

    Delta class (b): every registered example system that declares a
    `gateway {}` block has a genuinely gateway-deriving service -- no registered
    example was ever exposed via a name-based suppression heuristic and is now
    corrected by the derivation. That fixture (a service named e.g. "ingestion"
    behaving identically to a neutral-named sibling) lives in one fixture system
    per platform package, each in its own suite; this script does not fabricate a
    registered-example fixture for it (no cross-package tests), it reports the
    verified absence instead.

    Known pre-existing defects the gate meets are reported loudly in their own
    section and do NOT fail it: a defect that predates the ingress derivation and
    is independent of it is not an ingress regression.

    The last line is the gate verdict, "[GATE] ingress-migration-conformance
    PASSED|FAILED exit=<n> log=<path>"; the log holds the final ledger, the known
    defects and the findings.

.PARAMETER OutputRoot
    Scratch root for this gate's own regenerated output. Default:
    <workspace>\.test-output\ingress-gate (the repo temp-file policy).

.PARAMETER Languages
    Comma-separated codegen languages to sweep. Default: every registered
    datrix.languages target (discovered at runtime -- never a hardcoded list).

.PARAMETER DebugLogging
    Debug logging here and in every generation and the full-tree generation
    (alias -Dbg).

.PARAMETER SelfTest
    Run only the self-test and generate nothing: every check function over a
    planted file or tree that violates it records a finding, and over its
    compliant twin records none; plus the language list, the argument vectors,
    the design-directory exclusion, that the webhook artifacts delta (d) reads
    exist, and the wrapper seam.

.EXAMPLE
    .\ingress-migration-conformance-gate.ps1
    Run the full gate (every registered language) with default output root.

.EXAMPLE
    .\ingress-migration-conformance-gate.ps1 -Languages python
    Run the gate for Python only (faster iteration while debugging).

.EXAMPLE
    .\ingress-migration-conformance-gate.ps1 -SelfTest
    Prove every check on planted inputs.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$OutputRoot = "",

    [Parameter()]
    [string[]]$Languages = @(),

    [Alias("Dbg")]
    [switch]$DebugLogging,

    [Parameter()]
    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.realization.ingress_migration_conformance_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
