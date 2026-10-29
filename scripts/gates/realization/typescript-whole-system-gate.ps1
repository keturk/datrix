#!/usr/bin/env pwsh
<#
.SYNOPSIS
  REAL whole-system TypeScript generation gate: proves the whole-system generate
  path emits genuine TypeScript (not a hollow/failed run) and is byte-deterministic.

.DESCRIPTION
  Background: the whole-system generate path was
  hollow for TypeScript because the pipeline never attached the CodegenContext to
  the LANGUAGE generator -- Python received one only by a runtime_bootstrap
  side-effect, so TypeScriptGenerator's context stayed None and
  LanguageGenerator.generate raised "LanguageGenerator requires CodegenContext".
  With that fixed (datrix-cli pipeline/generation.py, _discover_language_and_generators)
  a real end-to-end TypeScript whole-system run is possible, and this gate proves it.

  The gate:
    1. Generates a LANGUAGE-NEUTRAL example project TWICE with --language typescript,
       into two explicit --output directories (run1 / run2), via the documented
       --source/--output single-project generation (the module behind
       dev\generate.ps1). The target language comes solely from that flag; no
       example pins a language, and none may -- a 'language' key in a system .dcfg
       is rejected at load time by datrix_common's system-config loader.
    2. REALNESS: asserts the run produced real TypeScript source (generated *.ts
       count > 0) AND that the SERVICE IMPLEMENTATION is TypeScript, not Python
       (no *.py under any generated `src/` tree -- the true hollow/leak guard).
    3. BYTE-STABILITY: recursively compares run1 vs run2 (sha256 per relative path).
       Any content or file-set difference fails the gate.

  WHY NOT a blanket "*.py == 0" over the whole tree: a TypeScript whole-system
  project legitimately contains LANGUAGE-AGNOSTIC Python artifacts, emitted by
  design for EVERY target language:
    - `tests/**` HTTP contract suite rendered by datrix-codegen-component's
      `contract_tests` domain, the same bytes for every backend language. These
      are black-box HTTP tests against the running service; they are not the
      service implementation.
  A blanket *.py==0 would therefore FAIL on correct, intended output. This gate
  instead pins the allowed Python location: any *.py OUTSIDE `tests/` (in
  particular any *.py under `src/`) is treated as a language leak and fails the
  gate.

  Excluded from BOTH the realness scan and the byte diff are non-source,
  post-generation build/install artifacts whose contents embed absolute paths or
  install state and are not deterministic generated source:
    .datrix  .ruff_cache  .tsc_cache  node_modules

  The last line is the gate verdict, "[GATE] typescript-whole-system PASSED|FAILED
  exit=<n> log=<path>"; the log holds the gate's output, the generations' included
  (each generation also keeps its own log under .generated\.results).

.PARAMETER OutputRoot
  Root under which run1/ and run2/ are written. Default:
  <workspace>/.test-output/ts-gate (per the repo temp-output policy).

.PARAMETER DebugLogging
  Debug logging here and in both generations (alias -Dbg).

.PARAMETER SelfTest
  Run only the self-test and generate nothing: the realness and byte-stability
  classifier over planted generation trees in a temp directory (a clean pair
  passes; a Python file under src/, a run with no .ts, a changed byte and a file
  only one run has each fail; differences inside an excluded directory do not),
  the path segments of a doubled separator, the tree walk, the generation
  argument vector, and the wrapper seam.

.EXAMPLE
  .\typescript-whole-system-gate.ps1
  Generate the example twice and check realness and byte-stability.

.EXAMPLE
  .\typescript-whole-system-gate.ps1 -SelfTest
  Prove the classifier on planted trees.
#>

[CmdletBinding()]
param(
    [Parameter()]
    [string]$OutputRoot = "",

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
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.realization.typescript_whole_system_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
