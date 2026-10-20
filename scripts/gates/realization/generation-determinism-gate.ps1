#!/usr/bin/env pwsh
<#
.SYNOPSIS
  Generation-pipeline determinism gate: the SAME source tree, generated N times
  in a row for one registered language via the documented single-project
  generation, must never produce two different outcomes.

.DESCRIPTION
  Background: a corpus generation sweep once found that running the IDENTICAL
  command against an UNCHANGED tree three times in a row produced THREE
  DIFFERENT outcomes -- once failing inside the language's own "generate:<lang>"
  pipeline stage (a struct-test planner unable to resolve a struct from the
  Application it was planned against), twice failing later at the generated
  project's compile step with a set of compiler errors. Same input, same
  invocation, different output: no conclusion drawn from one generation is
  trustworthy until this class of regression is caught automatically.

  Each run is its OWN generation process (a fresh Python interpreter running
  the module behind dev\generate.ps1), so this gate also exercises
  PYTHONHASHSEED-driven ordering bugs that a single long-lived process would
  never surface -- a `set` iterated without a deterministic sort produces
  different orderings across separate Python processes by default, but always
  the same ordering within one process. No before/after comparison of two code
  states can catch this class of bug, because it never runs the same code
  twice. This gate does: same code, N runs, N outcomes compared to each other.

  The gate:
    1. Generates the reference example N times (default 5) for -Language,
       into N explicit --output directories, via the documented
       --source/--output single-project mode.
    2. Each run is classified SUCCESS (generation + post-processing exited 0)
       or FAILED (non-zero exit), and a normalized fingerprint is computed:
         - SUCCESS: a per-relative-path sha256 manifest of the generated
           source tree, excluding `.datrix` (its own audit log / snapshot /
           manifest `generated_at` timestamp are expected to differ every
           run by design -- they record WHEN generation ran, not WHAT it
           produced).
         - FAILED: the run's own generation log, with its timestamp and log
           path lines dropped and the run's output directory path replaced by
           a fixed placeholder (so two runs failing for the identical reason
           in different --output directories fingerprint identically instead
           of spuriously differing on the run-specific path embedded in every
           compiler error line).
    3. All N runs must be the SAME classification, and all N fingerprints
       must be IDENTICAL. Any run whose classification or fingerprint differs
       from run 1 fails the gate and is reported by name.

  This gate does not require generation to currently SUCCEED for the
  reference example -- a consistent, reproducible FAILURE (same stage, same
  error, every run) is a passing outcome. The property under test is
  determinism, not correctness of the generated code; unrelated, already
  tracked codegen defects are out of this gate's scope.

  The last line is the gate verdict, "[GATE] generation-determinism
  PASSED|FAILED exit=<n> log=<path>"; the log holds the per-run outcomes and the
  findings (each generation keeps its own log under .generated\.results).

.PARAMETER Language
  Required unless -SelfTest. The registered `datrix.languages` name to generate
  for. There is no default: the gate never assumes which languages are
  installed.

.PARAMETER OutputRoot
  Root under which run1/ .. runN/ are written. Default:
  <workspace>/.test-output/generation-determinism-gate/<Language> (per the repo
  temp-output policy).

.PARAMETER Runs
  Number of repeated generations to compare. Default 5. Must be >= 2.

.PARAMETER DebugLogging
  Debug logging here and in every generation (alias -Dbg).

.PARAMETER SelfTest
  Run only the self-test and generate nothing: the success manifest and the
  failure fingerprint over planted trees and logs (one changed byte differs,
  identical twins and a different --output path do not), the outcome
  comparison (a changed classification or fingerprint fails, agreement
  passes), a run reading only the log it wrote, the tree walk, the generation
  argument vector, and the wrapper seam.

.EXAMPLE
  .\generation-determinism-gate.ps1 -Language python
  Generate the reference example five times for python and compare the outcomes.

.EXAMPLE
  .\generation-determinism-gate.ps1 -SelfTest
  Prove the fingerprints and the comparison on planted inputs.
#>

[CmdletBinding(DefaultParameterSetName = "Gate")]
param(
    [Parameter(Mandatory = $true, ParameterSetName = "Gate")]
    [string]$Language,

    [Parameter(ParameterSetName = "Gate")]
    [string]$OutputRoot,

    [Parameter(ParameterSetName = "Gate")]
    [int]$Runs = 5,

    [Parameter(ParameterSetName = "Gate")]
    [Alias("Dbg")]
    [switch]$DebugLogging,

    [Parameter(Mandatory = $true, ParameterSetName = "SelfTest")]
    [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.realization.generation_determinism_gate" -Parameters $PSBoundParameters
exit $LASTEXITCODE
