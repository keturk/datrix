#!/usr/bin/env pwsh
<#
.SYNOPSIS
 Author, migrate and check declarative test cases (datrix_testing.cases).

.DESCRIPTION
 Runs datrix_scripts.test.cases, which runs datrix_testing.cases.cli in the shared venv.
 A case is one row of a package's tests/cases/<area>.cases.yaml: a stage run
 on a committed input, one observed value, and an authored expectation. The
 package's one runner module, tests/test_cases.py, runs every row as a pytest
 item; this tool creates, inspects, migrates and checks them.

   observe  Run a stage and print the value a selector reads, with its parsed
            context. Writes nothing.
   new      Append one authored case to tests/cases/<area>.cases.yaml. Every
            field comes from you; the tool validates the row, refuses a known
            id or fact, resolves the selector, and appends it. Refused while
            the approval gate is armed for the package.
   migrate  Inventory every assertion of the named modules and write a
            proposal under D:\datrix\.tmp\case-proposals\ -- never into the
            repository.
            With -Annotations, propose moving the named modules' diagnostic,
            transpiled and language-server tests onto fixture annotations and
            per-code diagnostic fixtures instead.
   accept   Move an approved proposal's rows into case files (an annotation
            proposal's annotations and per-code fixtures into the fixtures),
            and remove the code they replace.
   check    Check everything the package commits about its cases: case files,
            fixture annotations, per-code fixtures and docs fences.

.PARAMETER Command
 observe, new, migrate, accept or check.

.PARAMETER Arguments
 The command's positional arguments:
   observe <input> <stage> <observer> <selector>      (with -Package)
   observe                                            (with -Package and -At <file>:<line>)
   new     <package> <area>                           (with the named fields)
   migrate <package> <module> ...
   migrate <package> <module> ...                     (with -Annotations)
   accept  <proposal> [<case id> ...]
   check   <package>

.PARAMETER Package
 observe: the package whose named inputs and registrations to load.

.PARAMETER At
 observe: a fixture line, <file>:<line>, in place of <input> <stage> <observer> <selector>;
 prints what each annotation kind would observe on that line (the diagnostics firing there,
 the code emitted for the function declared there, the language server's answers at its $0).

.PARAMETER Annotations
 migrate: propose fixture annotations (and per-code fixtures) for the named modules'
 diagnostic, transpiled and language-server tests, in place of case rows.

.PARAMETER Id
 new: the case id, <area>.<slug>.

.PARAMETER Tags
 new: the feature tags, comma-separated.

.PARAMETER CaseInput
 new: the named input (alias -Input).

.PARAMETER Stage
 new: the stage (generate, analyze, or one the package registers).

.PARAMETER Observer
 new: the observer kind.

.PARAMETER Selector
 new: the selector, a YAML flow mapping ({path: a, unit: statements, owner: f}).

.PARAMETER Expectation
 new: the expectation, a YAML flow value; omitted for an absent case.

.PARAMETER Reason
 new: one sentence naming the decision the case protects.

.PARAMETER Dbg
 Print the interpreter and the CLI arguments before the run.

.PARAMETER SelfTest
 Run the module's self-test (no -Command).

.EXAMPLE
 .\cases.ps1 check datrix-codegen-docker

.EXAMPLE
 .\cases.ps1 observe basic generate surface "{path: docker-compose.yml, unit: keys, key: [services]}" -Package datrix-codegen-docker

.EXAMPLE
 .\cases.ps1 new datrix-codegen-docker compose -Id compose.basic.api.port -Tags compose -Input basic -Stage generate -Observer surface -Selector "{path: docker-compose.yml, unit: value, key: [services, api, ports, '0']}" -Expectation "'8000:8000'" -Reason "The API is published on its service port."

.EXAMPLE
 .\cases.ps1 migrate datrix-codegen-typescript unit/auth/test_guard.py

.EXAMPLE
 .\cases.ps1 migrate datrix-semantic unit/validators/test_service_semver.py -Annotations

.EXAMPLE
 .\cases.ps1 accept D:\datrix\.tmp\case-proposals\datrix-codegen-typescript-modules-<hash>.proposal.json
#>
[CmdletBinding(DefaultParameterSetName = "Run")]
param(
 [Parameter(Position=0, Mandatory=$true, ParameterSetName="Run")]
 [ValidateSet("observe", "new", "migrate", "accept", "check")]
 [string]$Command,

 [Parameter(Position=1, ValueFromRemainingArguments=$true, ParameterSetName="Run")]
 [string[]]$Arguments,

 [Parameter(ParameterSetName="Run")][string]$Package,
 [Parameter(ParameterSetName="Run")][string]$Id,
 [Parameter(ParameterSetName="Run")][string]$Tags,
 [Parameter(ParameterSetName="Run")][Alias("Input")][string]$CaseInput,
 [Parameter(ParameterSetName="Run")][string]$Stage,
 [Parameter(ParameterSetName="Run")][string]$Observer,
 [Parameter(ParameterSetName="Run")][string]$Selector,
 [Parameter(ParameterSetName="Run")][string]$Expectation,
 [Parameter(ParameterSetName="Run")][string]$Reason,
 [Parameter(ParameterSetName="Run")][string]$At,
 [Parameter(ParameterSetName="Run")][switch]$Annotations,
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
Invoke-DatrixEntrypoint -Module "datrix_scripts.test.cases" -Parameters $PSBoundParameters
exit $LASTEXITCODE
