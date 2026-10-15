#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Run the affected set of Datrix package suites concurrently and return one verdict.

.DESCRIPTION
 Runs affected_gate.py in the shared venv. Runs the
 affected set: the changed packages plus the consumers named with -Consumers
 (packages whose suites reach the changed surface). Every other package in the
 changed packages' reverse-dependency closure is printed and recorded as
 excluded. Unless -All, one of -Consumers / -NoConsumers is required -- the
 consumer decision is never defaulted. Schedules `test.ps1 <pkg>` child
 processes longest-first under a
 PYTEST_XDIST_AUTO_NUM_WORKERS budget so concurrently running children never
 oversubscribe the machine, and aggregates one GREEN/RED verdict by reusing
 gate-verdict's own per-project evaluation. Writes affected-gate.json to
 <workspace>\.tmp\test\ by default. A plain-Python self-test suite runs
 automatically, unconditionally, as step 1 of every invocation.

 A human-only tool: it runs whole package suites, and no agent ever does.
 guard-full-suite-runs.py refuses every invocation from an agent tool call
 except -SelfTest. Agents verify a change with test.ps1 -Specific / -Tag.

.PARAMETER Projects
 One or more CHANGED package names (comma-separated or space-separated).

.PARAMETER Consumers
 Comma-separated packages, besides the changed ones, whose suites reach the
 changed surface (procedure: .claude/skills/_shared/verification-strategy.md,
 "Which packages a change reaches"). Required unless -NoConsumers or -All.

.PARAMETER NoConsumers
 State that no package besides the changed ones reaches the changed surface.

.PARAMETER All
 Treat every discovered package as changed.

.PARAMETER MaxConcurrent
 Optional cap on how many package suites run at once (default: no cap --
 children are admitted longest-first while their worker allotments fit in
 the logical core count). A cap, never a divisor of the cores.

.PARAMETER WorkersPerChild
 Uniform PYTEST_XDIST_AUTO_NUM_WORKERS override for every child, between 1
 and the logical core count (default: each package's share of the predicted
 CPU work, ceil(c / (sum(c) / cores)) clamped to [2, cores], where c is the
 package's newest full run's test_time_seconds).

.PARAMETER Mypy
 Also run mypy.ps1 for the CHANGED packages only, inside the same budget.

.PARAMETER Force
 Start even if a requested package's newest run looks in-progress.

.PARAMETER NoCarry
 Run every affected package, even one whose newest green full run's
 suite-input fingerprint still matches (flakiness hunts, a scheduled full
 sweep). Without it, such a package is CARRIED: its recorded run stands in and
 no child is launched for it.

.PARAMETER Output
 Output JSON path (default <workspace>\.tmp\test\affected-gate.json).

.PARAMETER SelfTest
 Run only the scheduler's own self-test suite and exit -- skips real
 scheduling. The same self-test also runs automatically, unconditionally, as
 step 1 of every normal invocation.

.PARAMETER Dbg
 Enable debug logging.

.EXAMPLE
 .\affected-gate.ps1 -Projects datrix-codegen-common -Consumers datrix-codegen-python,datrix-cli

.EXAMPLE
 .\affected-gate.ps1 -Projects datrix-codegen-typescript -NoConsumers

.EXAMPLE
 .\affected-gate.ps1 -All -MaxConcurrent 4 -Mypy
#>

[CmdletBinding()]
param(
    [Parameter(Position=0, ValueFromRemainingArguments=$true)]
    [string[]]$Projects,

    [string[]]$Consumers,

    [switch]$NoConsumers,

    [switch]$All,

    [int]$MaxConcurrent,

    [int]$WorkersPerChild,

    [switch]$Mypy,

    [switch]$Force,

    [switch]$NoCarry,

    [string]$Output,

    [switch]$SelfTest,

    [switch]$Dbg
)

$ErrorActionPreference = "Stop"
Import-Module (Join-Path $PSScriptRoot "..\common\DatrixPythonScript.psm1") -Force

$pythonArgs = @()
foreach ($project in $Projects) {
    if ($project) { $pythonArgs += @("--projects", $project) }
}
foreach ($consumer in $Consumers) {
    if ($consumer) { $pythonArgs += @("--consumers", $consumer) }
}
if ($NoConsumers) { $pythonArgs += "--no-consumers" }
if ($All) { $pythonArgs += "--all" }
if ($MaxConcurrent) { $pythonArgs += @("--max-concurrent", "$MaxConcurrent") }
if ($WorkersPerChild) { $pythonArgs += @("--workers-per-child", "$WorkersPerChild") }
if ($Mypy) { $pythonArgs += "--mypy" }
if ($Force) { $pythonArgs += "--force" }
if ($NoCarry) { $pythonArgs += "--no-carry" }
if ($Output) { $pythonArgs += @("--output", $Output) }
if ($SelfTest) { $pythonArgs += "--self-test" }
if ($Dbg) { $pythonArgs += "--debug" }

exit (Invoke-DatrixPythonScript -Script (Join-Path $PSScriptRoot "lib\affected_gate.py") -Arguments $pythonArgs -Gate "affected")
