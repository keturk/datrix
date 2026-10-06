#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Documentation-realization parity gate (Decision 39 I2/I6).

.DESCRIPTION
 For every registered `datrix.languages` target, generates one small fixture
 project -- via the real `datrix_cli.pipeline.generation.GenerationPipeline`
 (the exact code path `datrix generate`/`generate.ps1` runs), never a
 hand-built test context -- whose DSL documents an endpoint, an entity, a
 field, an enum value, a struct field and a function, each with a published
 (`///`) comment and an adjacent source-channel (`//`) comment. Asserts,
 by PARSING THE GENERATED ARTIFACTS STRUCTURALLY (Python's real `ast` +
 `tokenize`; a hand-rolled but genuinely structural bracket/string-aware
 lexer for C-family targets such as TypeScript -- never a line-oriented
 regex over the whole file), that the published text reaches that target's
 declared published surface and the source text reaches its source surface
 and NEVER the published one.

 This gate asserts over GENERATED ARTIFACTS, not a running service. Each
 language package proves a real end-to-end document in its own suite --
 python against a real FastAPI router's `.openapi()`, typescript against a
 real `tsc` + `SwaggerModule.createDocument()` run over an npm-installed
 dependency set. This gate is the repo-level cross-target census.

 The gate is a hard zero: every registered target realizes every
 (construct_kind, surface) cell, and an unpopulated cell is a hole that fails
 the gate naming the target, construct kind and surface. There is no
 exemption mechanism of any kind.

 Runs a SECOND comparison over the same generated fixture: the coverage
 census (Decision 39 invariant 1). It re-parses the fixture with the shipped
 capture pipeline, collects every comment run ATTACHED to a node, and counts
 how many reach no generated artifact at all on each target. Those counts are
 held by a decrease-only baseline in
 `datrix/scripts/config/documentation-coverage-baseline.json`; a target whose
 hole count rises above its pinned value fails the gate. (Attachment itself
 is policed separately, and at zero, by datrix-language's own
 produced-minus-consumed census -- this is the other half: attached, then
 dropped on the way to an artifact.)

 Derives its target set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded language-name literal -- so a future
 datrix-codegen-<lang> package is covered automatically with no edit here.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: every marker text is confirmed present in the fixture
 DSL itself, and each structural extractor (Python ast/tokenize, the
 C-family bracket/string-aware lexer and its doc-block reader) is proven
 against a synthetic snippet to find a known-present published/source text
 and to never leak a source comment into the published set, and a planted
 unpopulated cell is proven to fail the gate. Fails loud
 (exit 2) if fewer than 2 languages are registered.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO; also logs each target's
 discovered published-string set).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison (skips
 fixture generation entirely).

.PARAMETER UpdateCoverageBaseline
 Re-pin the decrease-only coverage-hole baseline to this run's measured
 per-target counts. The only writer of
 `datrix/scripts/config/documentation-coverage-baseline.json`; refuses to
 write when any target failed generation.

.EXAMPLE
 .\documentation-realization-parity-gate.ps1
 Run the gate for every registered language target.

.EXAMPLE
 .\documentation-realization-parity-gate.ps1 -SelfTest
 Run only the non-vacuity self-test.

.EXAMPLE
 .\documentation-realization-parity-gate.ps1 -Dbg
 Run the gate with debug logging.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [switch]$Dbg,

    [Parameter()]
    [switch]$SelfTest,

    [Parameter()]
    [switch]$UpdateCoverageBaseline
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$runnerScript = Join-Path $scriptDir "lib\documentation_realization_parity.py"

$commonDir = Join-Path $scriptDir "..\..\common"
Import-Module (Join-Path $commonDir "DatrixScriptCommon.psm1") -Force
. (Join-Path $commonDir "venv.ps1")

if (-not (Test-Path $runnerScript)) {
    Write-Error "Error: documentation_realization_parity.py not found at: $runnerScript"
    exit 1
}

function Invoke-Cleanup {
    Disable-DatrixVenv
}

trap {
    Invoke-Cleanup
    break
}

Ensure-DatrixVenv

try {
    Ensure-DatrixPackagesInstalled

    $pythonArgs = @($runnerScript)
    if ($Dbg) { $pythonArgs += "--debug" }
    if ($SelfTest) { $pythonArgs += "--self-test" }
    if ($UpdateCoverageBaseline) { $pythonArgs += "--update-coverage-baseline" }

    Write-Host "Running documentation-realization parity gate (all registered languages, Decision 39 I2/I6)" -ForegroundColor Cyan
    python @pythonArgs
    $exitCode = $LASTEXITCODE

    if ($exitCode -ne 0) {
        Write-Host "Documentation-realization parity gate failed with exit code $exitCode" -ForegroundColor Red
        exit $exitCode
    }

    Write-Host "Documentation-realization parity gate passed" -ForegroundColor Green
    exit 0
} finally {
    Invoke-Cleanup
}
