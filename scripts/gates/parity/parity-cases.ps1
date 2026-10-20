#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Author, migrate and check parity rows (gates\parity\cases\*.parity.yaml).

.DESCRIPTION
 A parity row is a case row (datrix_testing.cases) whose stage is 'parity' and whose
 observer is a conformance probe: one fact, read on every registered target of the
 probe's axis by parity-cases-gate.ps1 and compared with the authored expectation.

   observe  Build the fixture for every target and print each target's reading of a
            selector. Writes nothing (fixtures go under D:\datrix\.tmp\parity-cases).
   new      Validate one authored row, read it on every target, and append it to
            cases\<area>.parity.yaml. Refused while the approval gate is armed for the
            parity cases directory.
   migrate  Propose one row per selector a probe's return offers, with every target's
            reading beside it and no expectation, under D:\datrix\.tmp\case-proposals\.
            -Replaces names the probe-backed gate the rows replace.
   accept   Move an approved proposal's rows into cases\<area>.parity.yaml; refuses a
            proposal no approval covers and a row without an expectation. A proposal
            that replaces a gate also deletes the gate's wrapper, its .sh twin, the
            module it runs and its quick-reference section.
   check    Check every committed row.

 A missing field is a usage error (exit 2) before the tool runs.

.PARAMETER Command
 observe, new, migrate, accept or check.

.PARAMETER Arguments
 The command's positional arguments:
   observe <input> <probe> <selector>
   new     <area>                        (with the named fields)
   migrate <input> <probe>               (with -Area; -Tags and -Replaces optional)
   accept  <proposal>
   check

.PARAMETER Id
 new: the row id, <area>.<slug>.

.PARAMETER Tags
 new, migrate: the feature tags, comma-separated (new: every tag the row carries, 'parity'
 included; migrate: the behaviour tags added to 'parity').

.PARAMETER CaseInput
 new: the fixture (alias -Input): a registered example, or a header-set fixture.

.PARAMETER Probe
 new: the conformance probe method the row observes.

.PARAMETER Selector
 new: the selector, a YAML flow mapping ({facet: route, verb: get, path: /api/v1/books}).

.PARAMETER Expectation
 new: the expectation, a YAML flow value.

.PARAMETER Reason
 new: one sentence naming the decision the row protects.

.PARAMETER Area
 migrate: the area of the proposed rows (their file is cases\<area>.parity.yaml).

.PARAMETER Replaces
 migrate: the probe-backed gate the rows replace, by wrapper name without .ps1.

.PARAMETER Dbg
 Print the interpreter and the tool's arguments before the run.

.PARAMETER SelfTest
 Run the module's self-test (the command lines it builds, its usage refusals and the
 wrapper seam); runs no command.

.EXAMPLE
 .\parity-cases.ps1 observe rest-api route_wire_contracts "{facet: route, verb: get, path: /api/v1/books}"

.EXAMPLE
 .\parity-cases.ps1 migrate pubsub event_envelopes -Area events -Tags pubsub

.EXAMPLE
 .\parity-cases.ps1 check

.EXAMPLE
 .\parity-cases.ps1 -SelfTest
#>

[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position=0, Mandatory=$true, ParameterSetName="Run")]
 [ValidateSet("observe", "new", "migrate", "accept", "check")]
 [string]$Command,

 [Parameter(Position=1, ValueFromRemainingArguments=$true, ParameterSetName="Run")]
 [string[]]$Arguments,

 [Parameter(ParameterSetName="Run")][string]$Id,
 [Parameter(ParameterSetName="Run")][string]$Tags,
 [Parameter(ParameterSetName="Run")][Alias("Input")][string]$CaseInput,
 [Parameter(ParameterSetName="Run")][string]$Probe,
 [Parameter(ParameterSetName="Run")][string]$Selector,
 [Parameter(ParameterSetName="Run")][string]$Expectation,
 [Parameter(ParameterSetName="Run")][string]$Reason,
 [Parameter(ParameterSetName="Run")][string]$Area,
 [Parameter(ParameterSetName="Run")][string]$Replaces,
 [switch]$Dbg,

 [Parameter(Mandatory=$true, ParameterSetName="SelfTest")]
 [switch]$SelfTest
)
# Rendered from scripts/common/templates/entrypoint.ps1, as is every line from here on: the behaviour is the
# Python module named below, run in the shared venv with each bound parameter passed as --kebab-name.
$scripts = $PSScriptRoot
while ($scripts -and -not (Test-Path -LiteralPath (Join-Path $scripts "common\DatrixPythonScript.psm1"))) { $scripts = Split-Path -Parent $scripts }
if (-not $scripts) { throw "No datrix\scripts tree holds $PSCommandPath. Expected <workspace>\datrix\scripts\common\DatrixPythonScript.psm1 above it; run the wrapper from there." }
Import-Module (Join-Path $scripts "common\DatrixPythonScript.psm1")
Invoke-DatrixEntrypoint -Module "datrix_scripts.gates.parity.parity_cases" -Parameters $PSBoundParameters
exit $LASTEXITCODE
