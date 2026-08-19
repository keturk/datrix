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
 lexer for TypeScript/Java; real XML parsing of C#'s `///` doc-comment
 blocks -- never a line-oriented regex over the whole file), that the
 published text reaches that target's declared published surface and the
 source text reaches its source surface and NEVER the published one (I2).

 This gate asserts over GENERATED ARTIFACTS, not a running service: this
 sandbox has zero NuGet connectivity, so a generated .NET project can never
 be restored/built/started here. Each language package's own integration
 suite already proves a real end-to-end document (python: a real FastAPI
 router's `.openapi()`; typescript: a real `tsc` + `SwaggerModule
 .createDocument()` run; dotnet: a compiler-emitted XML doc file) -- this
 gate is the repo-level cross-target census, not a repeat of that per-
 package live proof.

 A target that does not yet realize a (construct_kind, surface) cell must
 carry a typed, reviewed exemption in
 `datrix/scripts/config/documentation-realization-exemptions.json`, whose
 `pinned_count` must equal the file's live entry count -- an unexempted hole
 fails the gate naming the target, construct kind and surface; a STALE
 exemption (the artifact now carries the text) also fails, naming the entry
 to remove.

 Derives its target set from
 `importlib.metadata.entry_points(group="datrix.languages")` at runtime --
 never a hardcoded python/typescript/java/dotnet literal -- so a future
 datrix-codegen-<lang> package is covered automatically with no edit here.

 Runs a built-in non-vacuity self-test on every invocation, before trusting
 any real comparison: every marker text is confirmed present in the fixture
 DSL itself, and each structural extractor (Python ast/tokenize, the
 C-family bracket/string-aware lexer, the dotnet XML-doc parser) is proven
 against a synthetic snippet to find a known-present published/source text
 and to never leak a source comment into the published set. Fails loud
 (exit 2) if fewer than 2 languages are registered.

 Repo-level validation script (per the datrix showcase boundary -- no
 pytest suite lives in datrix).

.PARAMETER Dbg
 Enable debug logging (DEBUG level instead of INFO; also logs each target's
 discovered published-string set).

.PARAMETER SelfTest
 Run only the non-vacuity self-test and skip the real comparison (skips
 fixture generation entirely).

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
    [switch]$SelfTest
)

$ErrorActionPreference = "Stop"

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$libraryDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\library"
$runnerScript = Join-Path $libraryDir "test\documentation_realization_parity.py"

$commonDir = Join-Path (Split-Path -Parent (Split-Path -Parent $scriptDir)) "scripts\common"
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
